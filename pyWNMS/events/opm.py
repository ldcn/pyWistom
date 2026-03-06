"""OPM-related event types.

Ports ``OpmChannelStatusPowerEvent``, ``OpmChannelStatusFreqEvent``,
``OpmChannelStatusOsnrEvent``, ``OpmNewChannelCountEvent``, and
``OpmNewChannelFoundEvent`` from the Java ``event/`` package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pyWNMS.events.base import Severity
from pyWNMS.events.wistom_event import WistomEvent, status_text, S_OK

if TYPE_CHECKING:
    from pyWNMS.models.configuration import WistomUnitConfiguration


class EventIsPortRelated:
    """Mixin for events that relate to a specific optical port."""

    def get_related_port(self) -> int:
        raise NotImplementedError


# -- OPM Channel Status sub-events ---------------------------------------

class _OpmChannelStatusBase(WistomEvent, EventIsPortRelated):
    """Base for the three OPM channel-status sub-events."""

    # Bitmasks for extracting individual sub-statuses from the combined
    # OPM status code (alarm_id 20).
    MASK_POWER = 0x00FF0000
    MASK_FREQ = 0x0000FF00
    MASK_OSNR = 0x000000FF

    _PREFIX = ""

    def __init__(self, id: int, sub_id: int, status_code: int,
                 timestamp: int,
                 config: Optional[WistomUnitConfiguration]) -> None:
        super().__init__(id, sub_id, status_code, timestamp)
        self.configuration = config
        self.port = 0
        if config:
            ch = config.get_channel_info(sub_id)
            if ch:
                self.port = ch.port

    def get_related_port(self) -> int:
        return self.port

    def get_description(self) -> str:
        port_desc = str(self.port)
        chan_desc = str(self.sub_id)
        if self.configuration:
            pi = self.configuration.get_port_info(self.port)
            if pi:
                port_desc = pi.description
            ci = self.configuration.get_channel_info(self.sub_id)
            if ci:
                chan_desc = ci.description
        return f"OPM Channel [{port_desc}.{chan_desc}]"

    def get_status(self) -> str:
        return f"{self._PREFIX}[{status_text(self.status_code)}]"


class OpmChannelStatusPowerEvent(_OpmChannelStatusBase):
    """OPM channel power-level alarm."""

    _PREFIX = "Power"

    def __init__(self, sub_id: int, status_code: int, timestamp: int,
                 config: Optional[WistomUnitConfiguration] = None) -> None:
        super().__init__(
            OpmChannelStatusPowerEvent.ID_OPM_POWER,
            sub_id, status_code, timestamp, config,
        )


class OpmChannelStatusFreqEvent(_OpmChannelStatusBase):
    """OPM channel frequency-offset alarm."""

    _PREFIX = "Freq"

    def __init__(self, sub_id: int, status_code: int, timestamp: int,
                 config: Optional[WistomUnitConfiguration] = None) -> None:
        super().__init__(
            OpmChannelStatusFreqEvent.ID_OPM_FREQ,
            sub_id, status_code, timestamp, config,
        )


class OpmChannelStatusOsnrEvent(_OpmChannelStatusBase):
    """OPM channel OSNR alarm."""

    _PREFIX = "OSNR"

    def __init__(self, sub_id: int, status_code: int, timestamp: int,
                 config: Optional[WistomUnitConfiguration] = None) -> None:
        super().__init__(
            OpmChannelStatusOsnrEvent.ID_OPM_OSNR,
            sub_id, status_code, timestamp, config,
        )


# -- New-channel events ---------------------------------------------------

class OpmNewChannelCountEvent(WistomEvent, EventIsPortRelated):
    """Change in total channel count on a port."""

    def __init__(self, sub_id: int, status_code: int, timestamp: int,
                 config: Optional[WistomUnitConfiguration] = None) -> None:
        super().__init__(
            OpmNewChannelCountEvent.ID_NEWCHANCOUNT,
            sub_id, status_code, timestamp,
        )
        self.configuration = config
        self.port = sub_id  # sub_id *is* the port for this event type

    def get_related_port(self) -> int:
        return self.port

    def get_description(self) -> str:
        return f"New channel count [port {self.port}]"

    def get_status(self) -> str:
        return str(self.status_code)

    def get_severity(self) -> Severity:
        return Severity.NA

    def is_stateless(self) -> bool:
        return True


class OpmNewChannelFoundEvent(WistomEvent, EventIsPortRelated):
    """Unconfigured channel detected on a port.

    The ``status_code`` encodes frequency (bits 0-17) and port
    (bits 18-21) as a bitmask when the event is first received.
    """

    FREQUENCY_MASK = 0x0003FFFF
    PORT_MASK = 0x003C0000

    def __init__(self, sub_id: int, status_code: int, timestamp: int,
                 config: Optional[WistomUnitConfiguration] = None) -> None:
        # Extract port and frequency from bitmask in status_code
        freq_raw = status_code & self.FREQUENCY_MASK
        port_raw = (status_code & self.PORT_MASK) >> 18

        super().__init__(
            OpmNewChannelFoundEvent.ID_NEWCHANFOUND,
            sub_id, status_code, timestamp,
        )
        self.configuration = config
        self.frequency = float(freq_raw)   # GHz
        self.port = port_raw

    def get_related_port(self) -> int:
        return self.port

    def set_related_port(self, port: int) -> None:
        self.port = port

    def set_frequency(self, freq: float) -> None:
        self.frequency = freq

    def get_description(self) -> str:
        return f"Unconfigured channel [port {self.port}, {self.frequency} GHz]"

    def get_status(self) -> str:
        if self.status_code == S_OK:
            return "Disappeared"
        return "Detected"

    def get_severity(self) -> Severity:
        if self.status_code == S_OK:
            return Severity.OK
        return Severity.ALARM
