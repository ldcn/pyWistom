"""TSV file writers for data logging.

Ports the Java data-logging methods from ``MonitorUnit`` — each writer
produces tab-separated files matching the Java WNMS format so existing
log analysis tools continue to work.

File naming conventions:
- Channel data: ``opmchanneldata_<YYYY-MM>.log``
- Total power:  ``<portId>_totalpower_<YYYY-MM>.log``
- Spectrum:     ``<portId>/<portId>_spectrum_<YYYY-MM>_<index>.log``
- Events:       ``events_<YYYY-MM>.log``
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pyWNMS.events.base import WnmsEvent
    from pyWNMS.models.data import (
        OpmChannelData, OpmSpectrumData, OpmTpwrData,
    )

logger = logging.getLogger(__name__)

_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_FILE_DATE_FMT = "%Y-%m"
_MAX_FILEINDEX = 100


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# ---- Event logger -------------------------------------------------------

class EventLogger:
    """Write event log entries as TSV.

    Output columns:
    ``Action \\t Timestamp \\t Id \\t SubId \\t Status \\t Description \\t
    StatusText \\t Acknowledged \\t Port``
    """

    _HEADER = (
        "Action\tTimestamp\tId\tSubId\tStatus\t"
        "Description\tStatusText\tAcknowledged\tPort\n"
    )

    def __init__(self, log_dir: str) -> None:
        self.log_dir = os.path.join(log_dir, "events")

    def write(self, event: WnmsEvent, action: str = "Raised") -> None:
        """Append one event entry to the log file."""
        _ensure_dir(self.log_dir)
        filename = f"events_{datetime.now().strftime(_FILE_DATE_FMT)}.log"
        filepath = os.path.join(self.log_dir, filename)

        write_header = not os.path.isfile(filepath)
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                if write_header:
                    f.write(self._HEADER)
                ts = event.raised.strftime(_DATE_FMT)
                ack = (event.acknowledged.strftime(_DATE_FMT)
                       if event.acknowledged else "")
                port = ""
                from pyWNMS.events.opm import EventIsPortRelated
                if isinstance(event, EventIsPortRelated):
                    port = str(event.get_related_port())
                f.write(
                    f"{action}\t{ts}\t{event.get_id()}\t"
                    f"{event.get_sub_id()}\t0x{event.status_code:x}\t"
                    f"{event.get_description()}\t{event.get_status()}\t"
                    f"{ack}\t{port}\n"
                )
        except Exception:
            logger.exception("Failed to write event log")


# ---- OPM channel data logger --------------------------------------------

class OpmChannelDataLogger:
    """Write OPM channel data as TSV.

    Output columns:
    ``Timestamp \\t ChannelId \\t PortId \\t CentralFreq \\t FWHM \\t
    Amplitude \\t CentralPower \\t OSNR \\t ChannelSpacing \\t
    StatusPower \\t StatusFreq \\t StatusOSNR \\t DeltaPower \\t
    DeltaFreq \\t OSNRMargin``
    """

    _HEADER = (
        "Timestamp\tChannelId\tPortId\tCentralFreq\tFWHM\t"
        "Amplitude\tCentralPower\tOSNR\tChannelSpacing\t"
        "StatusPower\tStatusFreq\tStatusOSNR\t"
        "DeltaPower\tDeltaFreq\tOSNRMargin\n"
    )

    def __init__(self, log_dir: str) -> None:
        self.log_dir = os.path.join(log_dir, "opmchanneldata")

    def write(self, data: OpmChannelData) -> None:
        """Append one channel data record."""
        _ensure_dir(self.log_dir)
        filename = (
            f"opmchanneldata_{datetime.now().strftime(_FILE_DATE_FMT)}.log")
        filepath = os.path.join(self.log_dir, filename)

        write_header = not os.path.isfile(filepath)
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                if write_header:
                    f.write(self._HEADER)
                ts = datetime.now().strftime(_DATE_FMT)
                f.write(
                    f"{ts}\t{data.channel_id}\t{data.port_id}\t"
                    f"{data.central_frequency}\t{data.fwhm}\t"
                    f"{data.amplitude}\t{data.central_power}\t"
                    f"{data.osnr}\t{data.channel_spacing}\t"
                    f"{data.status_power}\t{data.status_frequency}\t"
                    f"{data.status_osnr}\t{data.delta_power}\t"
                    f"{data.delta_frequency}\t{data.osnr_margin}\n"
                )
        except Exception:
            logger.exception("Failed to write channel data log")


# ---- Total power logger -------------------------------------------------

class OpmTpwrDataLogger:
    """Write total power measurements as TSV.

    Output columns:
    ``Timestamp \\t PortId \\t Power \\t StartInterval \\t EndInterval``
    """

    _HEADER = "Timestamp\tPortId\tPower\tStartInterval\tEndInterval\n"

    def __init__(self, log_dir: str) -> None:
        self.log_dir = os.path.join(log_dir, "totalpower")

    def write(self, data: OpmTpwrData) -> None:
        """Append one total-power record."""
        _ensure_dir(self.log_dir)
        filename = (
            f"{data.port_id}_totalpower_"
            f"{datetime.now().strftime(_FILE_DATE_FMT)}.log")
        filepath = os.path.join(self.log_dir, filename)

        write_header = not os.path.isfile(filepath)
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                if write_header:
                    f.write(self._HEADER)
                ts = datetime.now().strftime(_DATE_FMT)
                f.write(
                    f"{ts}\t{data.port_id}\t{data.power}\t"
                    f"{data.start_interval}\t{data.end_interval}\n"
                )
        except Exception:
            logger.exception("Failed to write tpwr data log")


# ---- Spectrum logger ----------------------------------------------------

class OpmSpectrumDataLogger:
    """Write spectrum data as TSV.

    Each port gets a subdirectory.  Files include a numeric index suffix
    to prevent excessive file sizes.

    Output columns:
    ``Frequency \\t Power``  (one row per sample)
    """

    _HEADER = "Frequency\tPower\n"

    def __init__(self, log_dir: str) -> None:
        self.log_dir = os.path.join(log_dir, "spectrum")

    def write(self, data: OpmSpectrumData) -> None:
        """Write a complete spectrum to a new file."""
        port_dir = os.path.join(self.log_dir, str(data.port_id))
        _ensure_dir(port_dir)

        date_str = datetime.now().strftime(_FILE_DATE_FMT)
        # Find next available file index
        for idx in range(_MAX_FILEINDEX):
            filename = (
                f"{data.port_id}_spectrum_{date_str}_{idx}.log")
            filepath = os.path.join(port_dir, filename)
            if not os.path.isfile(filepath):
                break
        else:
            # All indices used — overwrite the last one
            filepath = os.path.join(
                port_dir,
                f"{data.port_id}_spectrum_{date_str}_{_MAX_FILEINDEX - 1}.log")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self._HEADER)
                for freq, pwr in zip(data.frequency, data.power):
                    f.write(f"{freq}\t{pwr}\n")
        except Exception:
            logger.exception("Failed to write spectrum data log")
