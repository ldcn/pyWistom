"""MonitorEventModel — event store with deduplication, counters, triggers.

Ports the Java ``MonitorEventModel`` class.  Each MonitorUnit has its
own event model; counter changes propagate up the MonitorObject tree.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum, auto
from typing import (
    Callable, Dict, List, Optional, TYPE_CHECKING,
)

from pyWNMS.events.base import WnmsEvent, Severity
from pyWNMS.events.wistom_event import S_MISSING

if TYPE_CHECKING:
    from pyWNMS.events.opm import (
        OpmChannelStatusFreqEvent,
        OpmChannelStatusOsnrEvent,
        OpmChannelStatusPowerEvent,
        OpmNewChannelFoundEvent,
    )

logger = logging.getLogger(__name__)


class Counter(Enum):
    """Classification buckets for event counting."""
    PASSED = 0
    WARNINGS = 1
    ALARMS = 2
    ACKNOWLEDGED = 3


def _counter_for(event: WnmsEvent) -> Optional[Counter]:
    """Map an event to its counter bucket.

    Returns *None* if the event shouldn't be counted (stateless OK/NA
    events that have been acknowledged).
    """
    if event.is_acknowledged():
        if event.is_stateless() or event.get_severity() in (
                Severity.OK, Severity.NA):
            return None
        return Counter.ACKNOWLEDGED

    sev = event.get_severity()
    if sev in (Severity.OK, Severity.NA):
        return Counter.PASSED
    if sev == Severity.WARNING:
        return Counter.WARNINGS
    return Counter.ALARMS


class MonitorEventModel:
    """Stores, deduplicates, and classifies alarm/event instances.

    :param log_event_callback: Optional ``callback(event, text)`` for
        writing event log lines.
    :param trigger_callbacks: List of ``callback(event)`` for trigger
        actions (email, spectrum, tpwr).
    """

    def __init__(self) -> None:
        # Events keyed by hash_id for O(1) lookup / dedup
        self._events: Dict[int, WnmsEvent] = {}

        # Counters: base values from children + own events
        self._counters = {c: 0 for c in Counter}
        self._base_counters = {c: 0 for c in Counter}

        # Logging / trigger hooks (set by MonitorUnit)
        self.log_event_callback: Optional[
            Callable[[WnmsEvent, str], None]] = None
        self.trigger_callbacks: List[Callable[[WnmsEvent], None]] = []

        # Counter-change listeners (MonitorObject tree propagation)
        self._counter_listeners: List[Callable[[], None]] = []

    # ---- Counter access -------------------------------------------------

    def get_counter(self, counter: Counter) -> int:
        return self._counters.get(counter, 0)

    @property
    def total_alarms(self) -> int:
        return self._counters[Counter.ALARMS]

    @property
    def total_warnings(self) -> int:
        return self._counters[Counter.WARNINGS]

    @property
    def total_passed(self) -> int:
        return self._counters[Counter.PASSED]

    @property
    def total_acknowledged(self) -> int:
        return self._counters[Counter.ACKNOWLEDGED]

    # ---- Listener management --------------------------------------------

    def add_counter_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._counter_listeners:
            self._counter_listeners.append(callback)

    def remove_counter_listener(self, callback: Callable[[], None]) -> None:
        try:
            self._counter_listeners.remove(callback)
        except ValueError:
            pass

    def _fire_counter_changed(self) -> None:
        for cb in list(self._counter_listeners):
            try:
                cb()
            except Exception:
                logger.exception("Counter listener raised exception")

    # ---- Core add logic -------------------------------------------------

    def add(self, event: WnmsEvent, clear: bool = False) -> None:
        """Add or update an event in the model.

        This implements the Java ``MonitorEventModel.add()`` logic:

        1. Filter out OPM Freq/OSNR events with ``S_MISSING`` status.
        2. If hash_id exists: update statusCode, lastOccurrence.
        3. If new: only add if severity is not Ok/NA.
        4. On OPM Power with ``S_MISSING``: remove companion Freq/OSNR.
        5. Log and fire trigger callbacks.
        """
        # 1. Filter out OPM Freq/OSNR with S_MISSING
        if (event.id in (WnmsEvent.ID_OPM_FREQ, WnmsEvent.ID_OPM_OSNR)
                and event.status_code == S_MISSING):
            return

        existing = self._events.get(event.hash_id)

        if existing is not None:
            # Update existing event
            existing.status_code = event.status_code
            existing.set_last_occurrence()

            # Special case: OpmNewChannelFoundEvent OK copies port/freq
            if (event.id == WnmsEvent.ID_NEWCHANFOUND
                    and event.status_code == 0x01):
                from pyWNMS.events.opm import OpmNewChannelFoundEvent
                if (isinstance(event, OpmNewChannelFoundEvent)
                        and isinstance(existing, OpmNewChannelFoundEvent)):
                    existing.set_related_port(event.port)
                    existing.set_frequency(event.frequency)
        else:
            # New event — only add if not OK/NA
            sev = event.get_severity()
            if sev in (Severity.OK, Severity.NA) and not clear:
                return
            self._events[event.hash_id] = event

        # 4. OPM Power with S_MISSING → remove companion Freq/OSNR
        if (event.id == WnmsEvent.ID_OPM_POWER
                and event.status_code == S_MISSING):
            freq_hash = WnmsEvent.create_hash_id(
                WnmsEvent.ID_OPM_FREQ, event.sub_id)
            osnr_hash = WnmsEvent.create_hash_id(
                WnmsEvent.ID_OPM_OSNR, event.sub_id)
            self._events.pop(freq_hash, None)
            self._events.pop(osnr_hash, None)

        # 5. Log
        if self.log_event_callback:
            try:
                action = "Cleared" if clear else "Raised"
                self.log_event_callback(event, action)
            except Exception:
                logger.exception("Event log callback failed")

        # 6. Fire triggers
        for cb in self.trigger_callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Trigger callback failed")

        self._refresh_counters()

    # ---- Acknowledge / clear --------------------------------------------

    def acknowledge(self, event: WnmsEvent, signature: str,
                    date: Optional[datetime] = None) -> None:
        """Acknowledge an event."""
        ev = self._events.get(event.hash_id)
        if ev:
            ev.set_acknowledged(signature, date)
            self._refresh_counters()

    def acknowledge_all(self, signature: str) -> None:
        """Acknowledge all events."""
        for ev in self._events.values():
            if not ev.is_acknowledged():
                ev.set_acknowledged(signature)
        self._refresh_counters()

    def clear_passed(self) -> None:
        """Remove all clearable events (acknowledged + OK/NA)."""
        to_remove = [
            hid for hid, ev in self._events.items() if ev.is_clearable()
        ]
        for hid in to_remove:
            del self._events[hid]
        self._refresh_counters()

    def clear_event_if_passed(self, event: WnmsEvent) -> None:
        """Remove a single event if it is clearable."""
        ev = self._events.get(event.hash_id)
        if ev and ev.is_clearable():
            del self._events[event.hash_id]
            self._refresh_counters()

    def remove(self, hash_id: int) -> None:
        """Force-remove an event by hash_id."""
        if self._events.pop(hash_id, None) is not None:
            self._refresh_counters()

    def clear_all(self) -> None:
        """Remove all events."""
        self._events.clear()
        self._refresh_counters()

    # ---- Query ----------------------------------------------------------

    def get_events(self) -> List[WnmsEvent]:
        return list(self._events.values())

    def get_event(self, hash_id: int) -> Optional[WnmsEvent]:
        return self._events.get(hash_id)

    def __len__(self) -> int:
        return len(self._events)

    # ---- Counter refresh ------------------------------------------------

    def refresh_event_counters(
        self, passed: int = 0, warnings: int = 0,
        alarms: int = 0, acknowledged: int = 0,
    ) -> None:
        """Set base counters (from children), then add own events."""
        self._base_counters = {
            Counter.PASSED: passed,
            Counter.WARNINGS: warnings,
            Counter.ALARMS: alarms,
            Counter.ACKNOWLEDGED: acknowledged,
        }
        self._refresh_counters()

    def _refresh_counters(self) -> None:
        """Recompute counters from base + own events."""
        counts = dict(self._base_counters)
        for ev in self._events.values():
            bucket = _counter_for(ev)
            if bucket is not None:
                counts[bucket] = counts.get(bucket, 0) + 1
        old = dict(self._counters)
        self._counters = counts
        if counts != old:
            self._fire_counter_changed()
