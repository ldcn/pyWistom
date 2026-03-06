"""System-level and miscellaneous device events.

Ports ``TemperaturStatusEvent``, ``WistomSystemEvent``,
``WistomModuleStatus``, and ``UnknownWistomEvent``.
"""

from __future__ import annotations

from pyWNMS.events.base import WnmsEvent, Severity
from pyWNMS.events.wistom_event import WistomEvent


class TemperatureStatusEvent(WistomEvent):
    """Temperature alarm (alarm ID 30).

    :param sub_id: 1 = calibrated, 2 = user-configured limits.
    """

    SUBID_CALIBRATED = 1
    SUBID_USERCONF = 2

    def __init__(self, sub_id: int, status_code: int,
                 timestamp: int) -> None:
        super().__init__(WnmsEvent.ID_TEMP, sub_id, status_code, timestamp)

    def get_description(self) -> str:
        kind = ("Calibrated" if self.sub_id == self.SUBID_CALIBRATED
                else "User configured")
        return f"Temperature [{kind}]"


class WistomSystemEvent(WistomEvent):
    """System-level event (alarm ID 90).  Always stateless."""

    SUBID_ERRHANDLER = 1
    SUBID_SYSMANAGER = 2

    S_ERRHANDLER_ERRDUMPCREATED = 10
    S_SYSMANAGER_SAVE2FLASH = 4
    S_SYSMANAGER_SWUPGR_START = 10
    S_SYSMANAGER_SWUPGR_END = 11
    S_SYSMANAGER_SWUPGR_ABORT = 12

    def __init__(self, sub_id: int, status_code: int,
                 timestamp: int) -> None:
        super().__init__(
            WnmsEvent.ID_SYSTEMEVENT, sub_id, status_code, timestamp)

    def get_description(self) -> str:
        return "System event"

    def get_severity(self) -> Severity:
        return Severity.NA

    def is_stateless(self) -> bool:
        return True


class WistomModuleStatus(WistomEvent):
    """Module status event (alarm ID 91)."""

    SUBID_SWITCHMODULE = 1
    SUBID_SYSMGRMODULE = 2

    def __init__(self, sub_id: int, status_code: int,
                 timestamp: int) -> None:
        super().__init__(
            WnmsEvent.ID_MODULESTATUS, sub_id, status_code, timestamp)

    def get_description(self) -> str:
        name = {1: "Switch", 2: "System Manager"}.get(
            self.sub_id, f"Module {self.sub_id}")
        return f"Module status [{name}]"


class UnknownWistomEvent(WistomEvent):
    """Fallback for unrecognised alarm types."""

    def __init__(self, alarm_id: int, sub_id: int, status_code: int,
                 timestamp: int) -> None:
        super().__init__(alarm_id, sub_id, status_code, timestamp)

    def get_description(self) -> str:
        return f"Unknown event [id={self.id}, sub={self.sub_id}]"

    def get_severity(self) -> Severity:
        if self.is_acknowledged():
            return Severity.NA
        return Severity.WARNING

    def is_stateless(self) -> bool:
        return True
