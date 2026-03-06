"""Internal (non-device) events — connection and I/O errors.

Ports the Java ``ConnectionEvent`` and ``IOEvent`` classes.
"""

from __future__ import annotations

from pyWNMS.events.base import WnmsEvent, Severity


class InternalEvent(WnmsEvent):
    """Abstract base for events generated internally (not by device)."""

    SUBID_CONNECTION = 1
    SUBID_IOEXCEPTION = 2

    def __init__(self, sub_id: int, status_code: int) -> None:
        super().__init__(WnmsEvent.ID_INTERNAL, sub_id, status_code)

    def is_stateless(self) -> bool:
        return True


class ConnectionEvent(InternalEvent):
    """Login / logout / connection failure event.

    :param status_code: One of the ``IN_*`` / ``OUT_*`` constants.
    :param user_name: Username involved in the login attempt.
    """

    # Login result codes (positive = success levels)
    IN_USERLEVEL1 = 1
    IN_USERLEVEL2 = 2
    IN_USERLEVEL3 = 3
    IN_USERLEVEL4 = 4
    IN_USERLEVEL5 = 5

    # Login failure codes
    IN_MAXUSERS = 0x10000000
    IN_MAXUSERSINSYSTEM = 0x10000001
    IN_MAXLOGINATTEMPT = 0x10000002
    IN_PERMISSIONDENIED = 0x10000003
    IN_NOTFROMTHISIF = 0x10000004
    IN_INTERNAL1 = 0x10000005
    IN_INTERNAL2 = 0x10000006
    IN_WRONGPASSWORD = 0x10000007
    IN_UNKNOWNUSER = 0x10000008

    # Logout / disconnect codes
    OUT_BYUSER = 11
    OUT_NORESPONSE = 12
    OUT_BYREMOTE = 13
    OUT_UNEXPECTEDRESPONSE = 14
    OUT_UNKNOWN = 15

    _STATUS_MAP = {
        IN_USERLEVEL1: "Logged in (level 1)",
        IN_USERLEVEL2: "Logged in (level 2)",
        IN_USERLEVEL3: "Logged in (level 3)",
        IN_USERLEVEL4: "Logged in (level 4)",
        IN_USERLEVEL5: "Logged in (level 5)",
        IN_MAXUSERS: "Max users logged in",
        IN_MAXUSERSINSYSTEM: "Max users in system",
        IN_MAXLOGINATTEMPT: "Max login attempts exceeded",
        IN_PERMISSIONDENIED: "Permission denied",
        IN_NOTFROMTHISIF: "Not allowed from this interface",
        IN_INTERNAL1: "Internal error 1",
        IN_INTERNAL2: "Internal error 2",
        IN_WRONGPASSWORD: "Wrong password",
        IN_UNKNOWNUSER: "Unknown user",
        OUT_BYUSER: "Logged out by user",
        OUT_NORESPONSE: "No response from device",
        OUT_BYREMOTE: "Disconnected by remote",
        OUT_UNEXPECTEDRESPONSE: "Unexpected response",
        OUT_UNKNOWN: "Unknown disconnect reason",
    }

    def __init__(self, status_code: int,
                 user_name: str = "") -> None:
        super().__init__(InternalEvent.SUBID_CONNECTION, status_code)
        self.user_name = user_name

    def get_description(self) -> str:
        return f"Connection [{self.user_name}]"

    def get_status(self) -> str:
        return self._STATUS_MAP.get(
            self.status_code, f"Unknown({self.status_code})")

    def get_severity(self) -> Severity:
        # Normal login level → NA; user logout → NA; everything else → Alarm
        if 1 <= self.status_code <= 5:
            return Severity.NA
        if self.status_code == self.OUT_BYUSER:
            return Severity.NA
        return Severity.ALARM


class IOEvent(InternalEvent):
    """I/O error event (file write failures, trigger failures, etc.).

    :param status_code: One of the ``ERR_*`` constants.
    :param name: Descriptive name / context of the failed operation.
    :param cause: Exception message or further detail.
    """

    ERR_CREATEPATHFAIL = 1
    ERR_LOGEVENTFAIL = 2
    ERR_LOGDATAFAIL = 3
    ERR_TRIGGERSPECTRUM = 4
    ERR_TRIGGEREMAIL = 5
    ERR_TRIGGERTPWR = 6

    def __init__(self, status_code: int, name: str = "",
                 cause: str = "") -> None:
        super().__init__(InternalEvent.SUBID_IOEXCEPTION, status_code)
        self.name = name
        self.cause = cause

    def get_description(self) -> str:
        return f"IO error [{self.name}]: {self.cause}"

    def get_status(self) -> str:
        return self.cause or f"Error code {self.status_code}"

    def get_severity(self) -> Severity:
        if self.is_acknowledged():
            return Severity.NA
        return Severity.ALARM
