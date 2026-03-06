"""Data-logging pseudo-events (spectrum / total-power triggers)."""

from __future__ import annotations

from pyWNMS.events.base import WnmsEvent, Severity
from pyWNMS.events.opm import EventIsPortRelated


S_OK = 1
S_INVALIDDATA = 0x10


class _LogDataEvent(WnmsEvent, EventIsPortRelated):
    """Abstract base for data-log pseudo-events."""

    def __init__(self, id: int, sub_id: int, status_code: int) -> None:
        super().__init__(id, sub_id, status_code)
        self.port = sub_id

    def get_related_port(self) -> int:
        return self.port

    def get_severity(self) -> Severity:
        if self.status_code == S_OK:
            return Severity.OK
        return Severity.ALARM

    def is_stateless(self) -> bool:
        return True


class LogDataSpectrumEvent(_LogDataEvent):
    """Fired when a triggered spectrum capture completes."""

    def __init__(self, sub_id: int, status_code: int) -> None:
        super().__init__(
            WnmsEvent.ID_INT_LOGDATA_SPECTRUM, sub_id, status_code)

    def get_description(self) -> str:
        return f"Spectrum log [port {self.port}]"

    def get_status(self) -> str:
        if self.status_code == S_OK:
            return "OK"
        return "Invalid data"


class LogDataTpwrEvent(_LogDataEvent):
    """Fired when a triggered total-power capture completes."""

    def __init__(self, sub_id: int, status_code: int) -> None:
        super().__init__(
            WnmsEvent.ID_INT_LOGDATA_TPWR, sub_id, status_code)

    def get_description(self) -> str:
        return f"Total power log [port {self.port}]"

    def get_status(self) -> str:
        if self.status_code == S_OK:
            return "OK"
        return "Invalid data"
