"""OCM channel status event."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pyWNMS.events.base import WnmsEvent
from pyWNMS.events.wistom_event import WistomEvent, status_text
from pyWNMS.events.opm import EventIsPortRelated

if TYPE_CHECKING:
    from pyWNMS.models.configuration import WistomUnitConfiguration


class OcmChannelStatusEvent(WistomEvent, EventIsPortRelated):
    """OCM channel status alarm.

    :param sub_id: Channel number.
    :param status_code: Raw device status.
    :param timestamp: Epoch seconds.
    :param config: Unit configuration for port/channel name lookup.
    """

    def __init__(self, sub_id: int, status_code: int, timestamp: int,
                 config: Optional[WistomUnitConfiguration] = None) -> None:
        super().__init__(
            WnmsEvent.ID_OCM, sub_id, status_code, timestamp)
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
        return f"OCM Channel [{port_desc}.{chan_desc}]"

    def get_status(self) -> str:
        return status_text(self.status_code)
