"""WistomEvent — abstract base for device-originated events.

Ports the Java ``WistomEvent`` class including status-code constants,
human-readable status mapping, severity derivation, and the factory
method that creates concrete event instances from raw alarm data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from pyWNMS.events.base import WnmsEvent, Severity

if TYPE_CHECKING:
    from pyWNMS.models.configuration import WistomUnitConfiguration


# -- Status code constants ------------------------------------------------

S_OK = 0x01
S_MISSING = 0x04
S_NOTRESPONDING = 0x08
S_WARNING_LOW = 0x10
S_WARNING_HIGH = 0x20
S_ALARM_LOW = 0x40
S_ALARM_HIGH = 0x80
S_HWCOMMREADTMO = 0x100
S_HWCOMMWRITETMO = 0x200
S_HWCOMMREADERR = 0x400
S_HWCOMMWRITEERR = 0x800
S_UNSTABLE = 0x1000

_STATUS_TEXT = {
    S_OK: "OK",
    S_MISSING: "Missing",
    S_NOTRESPONDING: "Not responding",
    S_WARNING_LOW: "Warning low",
    S_WARNING_HIGH: "Warning high",
    S_ALARM_LOW: "Alarm low",
    S_ALARM_HIGH: "Alarm high",
    S_HWCOMMREADTMO: "HW comm read timeout",
    S_HWCOMMWRITETMO: "HW comm write timeout",
    S_HWCOMMREADERR: "HW comm read error",
    S_HWCOMMWRITEERR: "HW comm write error",
    S_UNSTABLE: "Unstable",
}


def status_text(code: int) -> str:
    """Map a raw status code to human-readable text."""
    return _STATUS_TEXT.get(code, f"Unknown(0x{code:x})")


def severity_from_status(code: int) -> Severity:
    """Derive :class:`Severity` from a device status code."""
    if code == S_OK:
        return Severity.OK
    if code in (S_WARNING_LOW, S_WARNING_HIGH):
        return Severity.WARNING
    # Everything else (missing, alarm, HW errors, unstable, …) is Alarm
    return Severity.ALARM


class WistomEvent(WnmsEvent):
    """Base for events originating from a Wistom device alarm message.

    :param id: Event type (alarm ID).
    :param sub_id: Element sub-identifier.
    :param status_code: Raw device status code.
    :param timestamp: Epoch seconds from the alarm message.
    """

    def __init__(self, id: int, sub_id: int, status_code: int,
                 timestamp: int = 0) -> None:
        super().__init__(id, sub_id, status_code)
        self.timestamp = timestamp

    def get_status(self) -> str:
        return status_text(self.status_code)

    def get_severity(self) -> Severity:
        return severity_from_status(self.status_code)

    def is_stateless(self) -> bool:
        return False

    # -- Factory ----------------------------------------------------------

    @staticmethod
    def instance_of(
        alarm_id: int,
        sub_id: int,
        status_code: int,
        timestamp: int,
        config: WistomUnitConfiguration | None = None,
    ) -> List[WnmsEvent]:
        """Create concrete event instances from a raw alarm element.

        For OPM alarms (ID 20), three events are returned (power,
        frequency, OSNR) because the status code packs all three
        sub-statuses as bit-fields.

        :returns: List of one or more :class:`WnmsEvent` instances.
        """
        # Import concrete types here to avoid circular imports
        from pyWNMS.events.opm import (
            OpmChannelStatusPowerEvent,
            OpmChannelStatusFreqEvent,
            OpmChannelStatusOsnrEvent,
            OpmNewChannelCountEvent,
            OpmNewChannelFoundEvent,
        )
        from pyWNMS.events.ocm import OcmChannelStatusEvent
        from pyWNMS.events.system import (
            TemperatureStatusEvent,
            WistomSystemEvent,
            WistomModuleStatus,
            UnknownWistomEvent,
        )

        if alarm_id == WnmsEvent.ID_OCM:
            return [OcmChannelStatusEvent(
                sub_id, status_code, timestamp, config)]

        if alarm_id == WnmsEvent.ID_OPM:
            # Three sub-events extracted via bitmask
            power_sc = (status_code >> 16) & 0xFF
            freq_sc = (status_code >> 8) & 0xFF
            osnr_sc = status_code & 0xFF
            return [
                OpmChannelStatusPowerEvent(
                    sub_id, power_sc, timestamp, config),
                OpmChannelStatusFreqEvent(
                    sub_id, freq_sc, timestamp, config),
                OpmChannelStatusOsnrEvent(
                    sub_id, osnr_sc, timestamp, config),
            ]

        if alarm_id == WnmsEvent.ID_NEWCHANCOUNT:
            return [OpmNewChannelCountEvent(
                sub_id, status_code, timestamp, config)]

        if alarm_id == WnmsEvent.ID_NEWCHANFOUND:
            return [OpmNewChannelFoundEvent(
                sub_id, status_code, timestamp, config)]

        if alarm_id == WnmsEvent.ID_TEMP:
            return [TemperatureStatusEvent(
                sub_id, status_code, timestamp)]

        if alarm_id == WnmsEvent.ID_SYSTEMEVENT:
            return [WistomSystemEvent(sub_id, status_code, timestamp)]

        if alarm_id == WnmsEvent.ID_MODULESTATUS:
            return [WistomModuleStatus(sub_id, status_code, timestamp)]

        return [UnknownWistomEvent(
            alarm_id, sub_id, status_code, timestamp)]
