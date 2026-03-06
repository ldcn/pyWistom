"""Base event class for all WNMS events.

Ports ``WnmsEvent`` from the Java ``event/`` package.  Every alarm,
connection state change, or I/O problem is represented as a subclass
of :class:`WnmsEvent`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional


class Severity(Enum):
    """Event severity level used for counter classification."""
    NA = "N/A"
    OK = "Ok"
    WARNING = "Warning"
    ALARM = "Alarm"


class WnmsEvent:
    """Abstract base for all WNMS events.

    :param id: Alarm / event type identifier.
    :param sub_id: Sub-identifier (e.g. channel number).
    :param status_code: Raw device status code.
    """

    # Well-known event type IDs
    ID_INTERNAL = 0
    ID_OCM = 10
    ID_OPM = 20
    ID_OPM_POWER = 0x10000 + 20   # 65556
    ID_OPM_OSNR = 0x20000 + 20    # 131092
    ID_OPM_FREQ = 0x30000 + 20    # 196628
    ID_NEWCHANCOUNT = 21
    ID_NEWCHANFOUND = 22
    ID_TEMP = 30
    ID_SYSTEMEVENT = 90
    ID_MODULESTATUS = 91
    ID_INT_LOGDATA_TPWR = 0x1001
    ID_INT_LOGDATA_SPECTRUM = 0x1002

    def __init__(self, id: int, sub_id: int, status_code: int) -> None:
        self.id = id
        self.sub_id = sub_id
        self.status_code = status_code
        self.hash_id: int = self.create_hash_id(id, sub_id)
        self.raised: datetime = datetime.now()
        self.last_occurrence: datetime = self.raised
        self.acknowledged: Optional[datetime] = None
        self.signature: Optional[str] = None

    # -- Hash / identity --------------------------------------------------

    @staticmethod
    def create_hash_id(id: int, sub_id: int) -> int:
        """Compute a unique hash for *(id, sub_id)* pair.

        .. note:: The Java version masks id to 16 bits which causes
           OPM Power/Freq/OSNR events to collide (they share the same
           lower 16 bits).  Python has arbitrary-precision ints so we
           use the full id to avoid the collision.
        """
        return (id << 16) + (sub_id & 0xFFFF)

    def get_id(self) -> int:
        return self.id & 0xFFFF

    def get_sub_id(self) -> int:
        return self.sub_id & 0xFFFF

    # -- Acknowledge workflow ---------------------------------------------

    def is_acknowledged(self) -> bool:
        return self.acknowledged is not None

    def set_acknowledged(self, signature: str,
                         date: Optional[datetime] = None) -> None:
        """Acknowledge this event (only sets once)."""
        if self.acknowledged is None:
            self.acknowledged = date or datetime.now()
            self.signature = signature

    def set_last_occurrence(self, when: Optional[datetime] = None) -> None:
        """Record a re-occurrence — resets the acknowledge state."""
        self.last_occurrence = when or datetime.now()
        self.acknowledged = None
        self.signature = None

    def is_clearable(self) -> bool:
        """True if the event can be removed from the model.

        An event is clearable when it has been acknowledged AND its
        severity is Ok or N/A.
        """
        return (self.is_acknowledged()
                and self.get_severity() in (Severity.OK, Severity.NA))

    # -- Abstract interface -----------------------------------------------

    def get_description(self) -> str:
        """Human-readable event description (override in subclass)."""
        return f"Event id={self.id} sub={self.sub_id}"

    def get_status(self) -> str:
        """Human-readable status text (override in subclass)."""
        return str(self.status_code)

    def get_severity(self) -> Severity:
        """Return the event severity (override in subclass)."""
        return Severity.NA

    def is_stateless(self) -> bool:
        """Stateless events do not persist in the event model."""
        return False

    # -- Comparison / sorting ---------------------------------------------

    def __lt__(self, other: WnmsEvent) -> bool:
        return self.hash_id < other.hash_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WnmsEvent):
            return NotImplemented
        return self.hash_id == other.hash_id

    def __hash__(self) -> int:
        return self.hash_id

    def __repr__(self) -> str:
        return (f"<{type(self).__name__} id={self.id} sub={self.sub_id} "
                f"status=0x{self.status_code:x}>")
