"""MonitorGroup — container for MonitorUnits with shared settings.

Ports the Java ``MonitorGroup`` class.  A group defines which alarm
types to subscribe and which OPM data to log, then propagates these
settings to all child :class:`MonitorUnit` objects.
"""

from __future__ import annotations

import logging
import os
from enum import Enum, auto
from typing import Optional

from pyWNMS.monitor.monitor_object import MonitorObject

logger = logging.getLogger(__name__)

# Default log interval: 24 hours in seconds
_DEFAULT_LOG_INTERVAL = 24 * 3600


class LogDataType(Enum):
    """Types of OPM data that can be periodically logged."""
    CHANNEL_DATA = auto()
    SPECTRUM = auto()
    TPWR = auto()


class MonitorGroup(MonitorObject):
    """Group node in the monitoring tree.

    :param name: Group display name.
    :param log_dir: Subdirectory name under the project log path.
    """

    def __init__(self, name: str = "", log_dir: str = "") -> None:
        super().__init__(name, log_dir)

        # Alarm subscription flags
        self.mon_ocm_alarm = False
        self.mon_opm_alarm = False
        self.mon_new_channel_count_alarm = False
        self.mon_new_channel_found_alarm = False
        self.mon_temp_alarm = False

        # Data logging flags
        self.log_event_to_disk = False
        self.log_opm_chan_data = False
        self.log_opm_spectrum_data = False
        self.log_opm_tpwr_data = False

        # Data logging intervals (seconds)
        self.log_opm_chan_data_interval = _DEFAULT_LOG_INTERVAL
        self.log_opm_spectrum_data_interval = _DEFAULT_LOG_INTERVAL
        self.log_opm_tpwr_data_interval = _DEFAULT_LOG_INTERVAL

        # Reference to project log root (set by project open)
        self._project_log_path: str = ""

    # ---- Log path -------------------------------------------------------

    def set_project_log_path(self, path: str) -> None:
        self._project_log_path = path

    def get_log_path(self) -> str:
        return os.path.join(self._project_log_path, self.log_dir)

    # ---- Alarm flag setters (propagate to children) ---------------------

    def set_mon_ocm_alarm(self, enabled: bool) -> None:
        self.mon_ocm_alarm = enabled
        self._update_children_monitored_events()

    def set_mon_opm_alarm(self, enabled: bool) -> None:
        self.mon_opm_alarm = enabled
        self._update_children_monitored_events()

    def set_mon_new_channel_count_alarm(self, enabled: bool) -> None:
        self.mon_new_channel_count_alarm = enabled
        self._update_children_monitored_events()

    def set_mon_new_channel_found_alarm(self, enabled: bool) -> None:
        self.mon_new_channel_found_alarm = enabled
        self._update_children_monitored_events()

    def set_mon_temp_alarm(self, enabled: bool) -> None:
        self.mon_temp_alarm = enabled
        self._update_children_monitored_events()

    def _update_children_monitored_events(self) -> None:
        """Push alarm subscription flags to all child MonitorUnits."""
        from pyWNMS.monitor.monitor_unit import MonitorUnit
        for child in self._children:
            if isinstance(child, MonitorUnit):
                child.sync_monitored_events(self)

    # ---- Data logging setters (propagate to children) -------------------

    def set_log_opm_chan_data(self, enabled: bool) -> None:
        self.log_opm_chan_data = enabled
        self._update_children_log_data()

    def set_log_opm_spectrum_data(self, enabled: bool) -> None:
        self.log_opm_spectrum_data = enabled
        self._update_children_log_data()

    def set_log_opm_tpwr_data(self, enabled: bool) -> None:
        self.log_opm_tpwr_data = enabled
        self._update_children_log_data()

    def _update_children_log_data(self) -> None:
        from pyWNMS.monitor.monitor_unit import MonitorUnit
        for child in self._children:
            if isinstance(child, MonitorUnit):
                child.sync_log_data(self)

    # ---- Override add to push settings to new children ------------------

    def add(self, child: MonitorObject) -> None:
        super().add(child)
        from pyWNMS.monitor.monitor_unit import MonitorUnit
        if isinstance(child, MonitorUnit):
            child.sync_monitored_events(self)
            child.sync_log_data(self)

    # ---- Serialization --------------------------------------------------

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "mon_ocm_alarm": self.mon_ocm_alarm,
            "mon_opm_alarm": self.mon_opm_alarm,
            "mon_new_channel_count_alarm": self.mon_new_channel_count_alarm,
            "mon_new_channel_found_alarm": self.mon_new_channel_found_alarm,
            "mon_temp_alarm": self.mon_temp_alarm,
            "log_event_to_disk": self.log_event_to_disk,
            "log_opm_chan_data": self.log_opm_chan_data,
            "log_opm_spectrum_data": self.log_opm_spectrum_data,
            "log_opm_tpwr_data": self.log_opm_tpwr_data,
            "log_opm_chan_data_interval": self.log_opm_chan_data_interval,
            "log_opm_spectrum_data_interval":
                self.log_opm_spectrum_data_interval,
            "log_opm_tpwr_data_interval": self.log_opm_tpwr_data_interval,
            "units": [c.to_dict() for c in self._children],
        })
        return base

    @classmethod
    def from_dict(cls, data: dict) -> MonitorGroup:
        g = cls(
            name=data.get("name", ""),
            log_dir=data.get("log_dir", ""),
        )
        g.mon_ocm_alarm = data.get("mon_ocm_alarm", False)
        g.mon_opm_alarm = data.get("mon_opm_alarm", False)
        g.mon_new_channel_count_alarm = data.get(
            "mon_new_channel_count_alarm", False)
        g.mon_new_channel_found_alarm = data.get(
            "mon_new_channel_found_alarm", False)
        g.mon_temp_alarm = data.get("mon_temp_alarm", False)
        g.log_event_to_disk = data.get("log_event_to_disk", False)
        g.log_opm_chan_data = data.get("log_opm_chan_data", False)
        g.log_opm_spectrum_data = data.get("log_opm_spectrum_data", False)
        g.log_opm_tpwr_data = data.get("log_opm_tpwr_data", False)
        g.log_opm_chan_data_interval = data.get(
            "log_opm_chan_data_interval", _DEFAULT_LOG_INTERVAL)
        g.log_opm_spectrum_data_interval = data.get(
            "log_opm_spectrum_data_interval", _DEFAULT_LOG_INTERVAL)
        g.log_opm_tpwr_data_interval = data.get(
            "log_opm_tpwr_data_interval", _DEFAULT_LOG_INTERVAL)
        return g
