"""MonitorObject — abstract base for the monitoring tree.

Both :class:`MonitorGroup` and :class:`MonitorUnit` inherit from this.
Objects form a parent→children tree.  Counter changes propagate upward.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from pyWNMS.monitor.monitor_event_model import Counter, MonitorEventModel

logger = logging.getLogger(__name__)


class MonitorObjectListener:
    """Protocol for observing monitor-object tree changes."""

    def monitor_object_state_changed(self, obj: MonitorObject) -> None:
        pass

    def monitor_object_properties_changed(
            self, obj: MonitorObject) -> None:
        pass

    def monitor_object_added(
            self, parent: MonitorObject, child: MonitorObject) -> None:
        pass

    def monitor_object_removed(
            self, parent: MonitorObject, child: MonitorObject) -> None:
        pass


class MonitorObject:
    """Abstract node in the monitoring tree.

    :param name: Display name (unique among siblings).
    :param log_dir: Directory name for log files.
    """

    def __init__(self, name: str = "", log_dir: str = "") -> None:
        self.name = name
        self.log_dir = log_dir
        self.parent: Optional[MonitorObject] = None
        self._children: List[MonitorObject] = []
        self.event_model = MonitorEventModel()

        # Trigger enable flags (per TriggerType)
        self._trigger_email: Dict[str, bool] = {}
        self._trigger_spectrum: Dict[str, bool] = {}
        self._trigger_tpwr: Dict[str, bool] = {}

        self._listeners: List[MonitorObjectListener] = []

    # ---- Children management --------------------------------------------

    @property
    def children(self) -> List[MonitorObject]:
        return list(self._children)

    def get_number_of_objects(self) -> int:
        return len(self._children)

    def contains(self, name: str) -> bool:
        return any(c.name == name for c in self._children)

    def get_child(self, name: str) -> Optional[MonitorObject]:
        for c in self._children:
            if c.name == name:
                return c
        return None

    def add(self, child: MonitorObject) -> None:
        """Add a child object after validation.

        :raises ValueError: If validation fails.
        """
        self.validate(None, child)
        child.parent = self
        self._children.append(child)
        self._children.sort(key=lambda o: o.name.lower())

        # Subscribe to child counter changes
        child.event_model.add_counter_listener(
            self._on_child_counter_changed)

        self._fire_added(child)
        self._refresh_counters()

    def remove(self, name: str) -> Optional[MonitorObject]:
        """Remove and release a child by name."""
        for i, c in enumerate(self._children):
            if c.name == name:
                child = self._children.pop(i)
                child.event_model.remove_counter_listener(
                    self._on_child_counter_changed)
                child.release_resources()
                self._fire_removed(child)
                self._refresh_counters()
                return child
        return None

    # ---- Validation -----------------------------------------------------

    def validate(self, exclude_name: Optional[str],
                 child: MonitorObject) -> None:
        if not child.name.strip():
            raise ValueError("Name must not be empty")
        if not child.log_dir.strip():
            raise ValueError("Log directory must not be empty")
        for existing in self._children:
            if exclude_name and existing.name == exclude_name:
                continue
            if existing.name == child.name:
                raise ValueError(
                    f"Name '{child.name}' already exists")

    def update(self, old_name: str, child: MonitorObject) -> None:
        self.validate(old_name, child)
        for i, c in enumerate(self._children):
            if c.name == old_name:
                self._children[i] = child
                child.parent = self
                self._children.sort(key=lambda o: o.name.lower())
                return
        raise ValueError(f"Child '{old_name}' not found")

    # ---- Counter propagation --------------------------------------------

    def _on_child_counter_changed(self) -> None:
        self._refresh_counters()

    def _refresh_counters(self) -> None:
        """Sum all children's counters and pass as base to own model."""
        passed = warnings = alarms = acknowledged = 0
        for c in self._children:
            passed += c.event_model.get_counter(Counter.PASSED)
            warnings += c.event_model.get_counter(Counter.WARNINGS)
            alarms += c.event_model.get_counter(Counter.ALARMS)
            acknowledged += c.event_model.get_counter(Counter.ACKNOWLEDGED)
        self.event_model.refresh_event_counters(
            passed, warnings, alarms, acknowledged)

    # ---- Trigger enables (per TriggerType name) -------------------------

    def set_trigger_email_enabled(
            self, trigger_type: str, enabled: bool) -> None:
        self._trigger_email[trigger_type] = enabled

    def is_trigger_email_enabled(self, trigger_type: str) -> bool:
        return self._trigger_email.get(trigger_type, False)

    def set_trigger_spectrum_enabled(
            self, trigger_type: str, enabled: bool) -> None:
        self._trigger_spectrum[trigger_type] = enabled

    def is_trigger_spectrum_enabled(self, trigger_type: str) -> bool:
        return self._trigger_spectrum.get(trigger_type, False)

    def set_trigger_tpwr_enabled(
            self, trigger_type: str, enabled: bool) -> None:
        self._trigger_tpwr[trigger_type] = enabled

    def is_trigger_tpwr_enabled(self, trigger_type: str) -> bool:
        return self._trigger_tpwr.get(trigger_type, False)

    # ---- Listener management --------------------------------------------

    def add_listener(self, listener: MonitorObjectListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: MonitorObjectListener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def _fire_state_changed(self) -> None:
        for ls in list(self._listeners):
            try:
                ls.monitor_object_state_changed(self)
            except Exception:
                logger.exception("MonitorObject listener error")

    def _fire_properties_changed(self) -> None:
        for ls in list(self._listeners):
            try:
                ls.monitor_object_properties_changed(self)
            except Exception:
                logger.exception("MonitorObject listener error")

    def _fire_added(self, child: MonitorObject) -> None:
        for ls in list(self._listeners):
            try:
                ls.monitor_object_added(self, child)
            except Exception:
                logger.exception("MonitorObject listener error")

    def _fire_removed(self, child: MonitorObject) -> None:
        for ls in list(self._listeners):
            try:
                ls.monitor_object_removed(self, child)
            except Exception:
                logger.exception("MonitorObject listener error")

    # ---- Abstract / overridable -----------------------------------------

    def release_resources(self) -> None:
        """Release timers, listeners, connections (override)."""
        for c in self._children:
            c.release_resources()

    def get_log_path(self) -> str:
        """Return the full log path for this object (override)."""
        return self.log_dir

    # ---- Serialization --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "log_dir": self.log_dir,
        }

    # ---- Display --------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{type(self).__name__} '{self.name}'>"

    def __lt__(self, other: MonitorObject) -> bool:
        return self.name.lower() < other.name.lower()
