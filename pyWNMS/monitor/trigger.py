"""Trigger actions — email, spectrum capture, total-power capture.

Ports the Java ``MonitorTriggerAction``, ``TriggerActionEmail``,
``TriggerActionSpectrum``, and ``TriggerActionTpwr`` classes.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto
from typing import Dict, Optional, TYPE_CHECKING

from pyWNMS.events.base import WnmsEvent, Severity

if TYPE_CHECKING:
    from pyWNMS.unit.wistom_unit import WistomUnit, WistomUnitCommListener
    from pyWNMS.util.email_client import EmailClient

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Categories of events that can fire trigger actions."""
    SYSTEM = auto()
    OPM_CHANNEL_MISSING = auto()
    OPM_CHANNEL_ALARM = auto()
    OPM_CHANNEL_WARNING = auto()
    NEW_CHANNEL_COUNT = auto()
    UNCONFIGURED_CHANNEL_DETECTED = auto()


class HoldOffTimer:
    """Per-port hold-off to prevent trigger action storms."""

    def __init__(self) -> None:
        self._timers: Dict[int, float] = {}  # port → expiry timestamp

    def is_active(self, port: int) -> bool:
        expiry = self._timers.get(port)
        if expiry is None:
            return False
        if time.monotonic() >= expiry:
            del self._timers[port]
            return False
        return True

    def start(self, port: int, hold_off_seconds: float) -> None:
        self._timers[port] = time.monotonic() + hold_off_seconds


def _classify_event(event: WnmsEvent) -> Optional[TriggerType]:
    """Determine the trigger type for an event."""
    from pyWNMS.events.opm import (
        OpmNewChannelCountEvent,
        OpmNewChannelFoundEvent,
        EventIsPortRelated,
    )
    from pyWNMS.events.system import WistomSystemEvent, WistomModuleStatus
    from pyWNMS.events.wistom_event import S_MISSING

    if isinstance(event, (WistomSystemEvent, WistomModuleStatus)):
        return TriggerType.SYSTEM

    # OPM channel status events
    from pyWNMS.events.opm import _OpmChannelStatusBase
    if isinstance(event, _OpmChannelStatusBase):
        if event.status_code == S_MISSING:
            return TriggerType.OPM_CHANNEL_MISSING
        sev = event.get_severity()
        if sev == Severity.ALARM:
            return TriggerType.OPM_CHANNEL_ALARM
        if sev == Severity.WARNING:
            return TriggerType.OPM_CHANNEL_WARNING
        return None

    if isinstance(event, OpmNewChannelCountEvent):
        return TriggerType.NEW_CHANNEL_COUNT

    if isinstance(event, OpmNewChannelFoundEvent):
        if event.get_severity() == Severity.ALARM:
            return TriggerType.UNCONFIGURED_CHANNEL_DETECTED
        return None

    return None


def _get_event_port(event: WnmsEvent) -> int:
    """Extract the related port from an event (0 for system-level)."""
    from pyWNMS.events.opm import EventIsPortRelated
    if isinstance(event, EventIsPortRelated):
        return event.get_related_port()
    return 0


class MonitorTriggerAction:
    """Base class for trigger actions with per-type enables and hold-off.

    :param unit: The WistomUnit that originated the event.
    :param hold_off_time: Hold-off duration in seconds.
    """

    def __init__(self, unit: Optional[WistomUnit] = None,
                 hold_off_time: float = 5.0) -> None:
        self.unit = unit
        self.hold_off_time = hold_off_time
        self._enabled: Dict[TriggerType, bool] = {
            t: False for t in TriggerType}
        self._hold_off = HoldOffTimer()

    def set_enabled(self, trigger_type: TriggerType,
                    enabled: bool) -> None:
        self._enabled[trigger_type] = enabled

    def is_enabled(self, trigger_type: TriggerType) -> bool:
        return self._enabled.get(trigger_type, False)

    def trigger(self, event: WnmsEvent) -> bool:
        """Check if this event should fire the action.

        Returns *True* if the action was triggered.
        """
        tt = _classify_event(event)
        if tt is None or not self._enabled.get(tt, False):
            return False

        port = _get_event_port(event)
        if self._hold_off.is_active(port):
            return False

        self._hold_off.start(port, self.hold_off_time)
        return True

    def execute(self, event: WnmsEvent) -> None:
        """Execute the trigger action (override in subclass)."""
        raise NotImplementedError


class TriggerActionEmail(MonitorTriggerAction):
    """Send an email notification when triggered."""

    def __init__(self, unit: Optional[WistomUnit] = None,
                 email_client: Optional[EmailClient] = None,
                 monitor_unit_name: str = "",
                 hold_off_time: float = 5.0) -> None:
        super().__init__(unit, hold_off_time)
        self.email_client = email_client
        self.monitor_unit_name = monitor_unit_name

    def execute(self, event: WnmsEvent) -> None:
        if not self.trigger(event):
            return
        if self.email_client is None:
            return

        subject = "WNMS event"
        body = (f"{self.monitor_unit_name}: "
                f"{event.get_description()} {event.get_status()}")

        def _send():
            try:
                self.email_client.send(subject, body)
            except Exception:
                logger.exception("Trigger email failed")

        t = threading.Thread(target=_send, daemon=True)
        t.start()


class TriggerActionSpectrum(MonitorTriggerAction):
    """Request a spectrum capture when triggered."""

    def __init__(self, unit: Optional[WistomUnit] = None,
                 receiver: Optional[WistomUnitCommListener] = None,
                 hold_off_time: float = 5.0) -> None:
        super().__init__(unit, hold_off_time)
        self.receiver = receiver

    def execute(self, event: WnmsEvent) -> None:
        if not self.trigger(event):
            return
        port = _get_event_port(event)
        if port > 0 and self.unit and self.receiver:
            try:
                self.unit.request_spectrum_data(self.receiver, port, event)
            except Exception:
                logger.exception("Trigger spectrum request failed")


class TriggerActionTpwr(MonitorTriggerAction):
    """Request a total-power capture when triggered."""

    def __init__(self, unit: Optional[WistomUnit] = None,
                 receiver: Optional[WistomUnitCommListener] = None,
                 hold_off_time: float = 5.0) -> None:
        super().__init__(unit, hold_off_time)
        self.receiver = receiver

    def execute(self, event: WnmsEvent) -> None:
        if not self.trigger(event):
            return
        port = _get_event_port(event)
        if port > 0 and self.unit and self.receiver:
            try:
                self.unit.request_tpwr_data(self.receiver, port, event)
            except Exception:
                logger.exception("Trigger tpwr request failed")
