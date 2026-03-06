"""MonitorUnit — per-device monitoring node with data logging and triggers.

Ports the Java ``MonitorUnit`` class.  A MonitorUnit wraps a
:class:`WistomUnit`, subscribes to its events and data, runs periodic
data collection timers, and writes log files.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

from pyWNMS.events.base import WnmsEvent, Severity
from pyWNMS.events.internal import ConnectionEvent
from pyWNMS.events.wistom_event import WistomEvent
from pyWNMS.models.data import (
    OpmChannelData, OpmChannelDataCollection,
    OpmSpectrumData, OpmTpwrData,
)
from pyWNMS.monitor.monitor_object import MonitorObject
from pyWNMS.unit.wistom_unit import (
    OptionalEvent, UnitState, WistomUnit,
    WistomUnitCommListener, WistomUnitListener,
)

if TYPE_CHECKING:
    from pyWNMS.monitor.monitor_group import MonitorGroup, LogDataType

logger = logging.getLogger(__name__)

# First-time delay before starting data collection (seconds)
_DATA_LOG_FIRST_DELAY = 0.5
_DATA_LOG_MAX_FILEINDEX = 100


class MonitorUnit(
    MonitorObject,
    WistomUnitListener,
    WistomUnitCommListener,
):
    """Monitoring proxy for a single :class:`WistomUnit`.

    :param name: Display name.
    :param log_dir: Log subdirectory name.
    :param unit: The Wistom device to monitor.
    """

    def __init__(self, name: str = "", log_dir: str = "",
                 unit: Optional[WistomUnit] = None) -> None:
        super().__init__(name, log_dir)
        self.unit = unit
        self._monitor_group: Optional[MonitorGroup] = None

        # Per-optional-event subscription flags
        self._monitored_events = {e: False for e in OptionalEvent}

        # Data logging flags
        self._log_channel_data = False
        self._log_spectrum_data = False
        self._log_tpwr_data = False

        # Periodic data collection timers
        self._log_timers: dict = {}

        # Register as listener on the WistomUnit
        if self.unit:
            self.unit.add_unit_listener(self)
            self.unit.add_comm_listener(self)

    # ---- Parent association ---------------------------------------------

    def set_parent_group(self, group: MonitorGroup) -> None:
        self._monitor_group = group
        self.parent = group

    # ---- Sync settings from MonitorGroup --------------------------------

    def sync_monitored_events(self, group: MonitorGroup) -> None:
        """Apply the group's alarm subscription flags."""
        self._set_monitor_event(OptionalEvent.OCM, group.mon_ocm_alarm)
        self._set_monitor_event(OptionalEvent.OPM, group.mon_opm_alarm)
        self._set_monitor_event(
            OptionalEvent.NEW_CHANNEL_COUNT,
            group.mon_new_channel_count_alarm)
        self._set_monitor_event(
            OptionalEvent.NEW_CHANNEL_FOUND,
            group.mon_new_channel_found_alarm)
        self._set_monitor_event(
            OptionalEvent.TEMPERATURE, group.mon_temp_alarm)

    def sync_log_data(self, group: MonitorGroup) -> None:
        """Apply the group's data-logging flags."""
        from pyWNMS.monitor.monitor_group import LogDataType
        self._log_channel_data = group.log_opm_chan_data
        self._log_spectrum_data = group.log_opm_spectrum_data
        self._log_tpwr_data = group.log_opm_tpwr_data
        self._reschedule_all_timers()

    # ---- Event subscription management ----------------------------------

    def _set_monitor_event(self, opt: OptionalEvent,
                           enabled: bool) -> None:
        old = self._monitored_events.get(opt, False)
        self._monitored_events[opt] = enabled
        if self.unit:
            if enabled and not old:
                self.unit.enable_monitor_of_event(opt)
            elif not enabled and old:
                self.unit.disable_monitor_of_event(opt)

    # ---- WistomUnitListener callbacks -----------------------------------

    def wistom_unit_state_changed(
            self, unit: WistomUnit, cause: str = "") -> None:
        if unit.state == UnitState.CONNECTED:
            self._reschedule_all_timers()
        else:
            self._cancel_all_timers()
        self._fire_state_changed()

    def wistom_unit_properties_changed(
            self, unit: WistomUnit) -> None:
        self._fire_properties_changed()

    def wistom_unit_configuration_changed(
            self, unit: WistomUnit) -> None:
        self._fire_state_changed()

    # ---- WistomUnitCommListener callbacks --------------------------------

    def wistom_unit_comm_event_received(
            self, unit: WistomUnit, event: WnmsEvent) -> None:
        """Receive an event from the unit and add to event model."""
        # Clear events on login
        if isinstance(event, ConnectionEvent):
            if 1 <= event.status_code <= 5:
                self.event_model.clear_all()

        # Filter: only pass events for subscribed types
        if self._should_process_event(event):
            self.event_model.add(event)

    def wistom_unit_comm_data_received(
            self, unit: WistomUnit, data: Any) -> None:
        """Receive measurement data from the unit."""
        if isinstance(data, OpmChannelDataCollection):
            self._on_channel_data(data)
        elif isinstance(data, OpmTpwrData):
            self._on_tpwr_data(data)
        elif isinstance(data, OpmSpectrumData):
            self._on_spectrum_data(data)

    # ---- Event filtering ------------------------------------------------

    def _should_process_event(self, event: WnmsEvent) -> bool:
        """Check if this event type is subscribed."""
        # Connection events always pass through
        if isinstance(event, ConnectionEvent):
            return True
        # System + Module always subscribed
        if event.get_id() in (WnmsEvent.ID_SYSTEMEVENT,
                              WnmsEvent.ID_MODULESTATUS):
            return True
        # Check optional subscriptions
        eid = event.get_id()
        opt_map = {
            WnmsEvent.ID_OCM: OptionalEvent.OCM,
            WnmsEvent.ID_OPM: OptionalEvent.OPM,
            WnmsEvent.ID_OPM_POWER: OptionalEvent.OPM,
            WnmsEvent.ID_OPM_FREQ: OptionalEvent.OPM,
            WnmsEvent.ID_OPM_OSNR: OptionalEvent.OPM,
            WnmsEvent.ID_NEWCHANCOUNT: OptionalEvent.NEW_CHANNEL_COUNT,
            WnmsEvent.ID_NEWCHANFOUND: OptionalEvent.NEW_CHANNEL_FOUND,
            WnmsEvent.ID_TEMP: OptionalEvent.TEMPERATURE,
        }
        opt = opt_map.get(eid)
        if opt:
            return self._monitored_events.get(opt, False)
        return True

    # ---- Data handlers --------------------------------------------------

    def _on_channel_data(self, data: OpmChannelDataCollection) -> None:
        """Handle received channel data — log if enabled."""
        if self._log_channel_data and data.channels:
            from pyWNMS.datalog.writers import OpmChannelDataLogger
            try:
                log_path = self._get_data_log_path()
                writer = OpmChannelDataLogger(log_path)
                for ch in data.channels:
                    writer.write(ch)
            except Exception:
                logger.exception("Failed to log channel data")

    def _on_tpwr_data(self, data: OpmTpwrData) -> None:
        if self._log_tpwr_data and data.valid:
            from pyWNMS.datalog.writers import OpmTpwrDataLogger
            try:
                log_path = self._get_data_log_path()
                writer = OpmTpwrDataLogger(log_path)
                writer.write(data)
            except Exception:
                logger.exception("Failed to log tpwr data")

    def _on_spectrum_data(self, data: OpmSpectrumData) -> None:
        if self._log_spectrum_data and data.valid:
            from pyWNMS.datalog.writers import OpmSpectrumDataLogger
            try:
                log_path = self._get_data_log_path()
                writer = OpmSpectrumDataLogger(log_path)
                writer.write(data)
            except Exception:
                logger.exception("Failed to log spectrum data")

    def _get_data_log_path(self) -> str:
        if self._monitor_group:
            return os.path.join(
                self._monitor_group.get_log_path(), self.log_dir)
        return self.log_dir

    # ---- Periodic data collection timers --------------------------------

    def _reschedule_all_timers(self) -> None:
        self._cancel_all_timers()
        if not self.unit or self.unit.state != UnitState.CONNECTED:
            return
        if self._log_channel_data and self._monitor_group:
            self._start_timer(
                "channel_data",
                self._monitor_group.log_opm_chan_data_interval,
                self._timer_request_channel_data)
        if self._log_spectrum_data and self._monitor_group:
            self._start_timer(
                "spectrum",
                self._monitor_group.log_opm_spectrum_data_interval,
                self._timer_request_spectrum)
        if self._log_tpwr_data and self._monitor_group:
            self._start_timer(
                "tpwr",
                self._monitor_group.log_opm_tpwr_data_interval,
                self._timer_request_tpwr)

    def _start_timer(self, key: str, interval: float,
                     callback) -> None:
        t = threading.Timer(_DATA_LOG_FIRST_DELAY, callback,
                            kwargs={"interval": interval})
        t.daemon = True
        t.start()
        self._log_timers[key] = t

    def _cancel_all_timers(self) -> None:
        for t in self._log_timers.values():
            t.cancel()
        self._log_timers.clear()

    def _timer_request_channel_data(self, interval: float) -> None:
        if self.unit and self.unit.state == UnitState.CONNECTED:
            self.unit.request_channel_data(self)
            # Reschedule
            t = threading.Timer(interval, self._timer_request_channel_data,
                                kwargs={"interval": interval})
            t.daemon = True
            t.start()
            self._log_timers["channel_data"] = t

    def _timer_request_spectrum(self, interval: float) -> None:
        if self.unit and self.unit.state == UnitState.CONNECTED:
            cfg = self.unit.configuration
            for port in cfg.ports:
                self.unit.request_spectrum_data(self, port)
            t = threading.Timer(interval, self._timer_request_spectrum,
                                kwargs={"interval": interval})
            t.daemon = True
            t.start()
            self._log_timers["spectrum"] = t

    def _timer_request_tpwr(self, interval: float) -> None:
        if self.unit and self.unit.state == UnitState.CONNECTED:
            cfg = self.unit.configuration
            for port in cfg.ports:
                self.unit.request_tpwr_data(self, port)
            t = threading.Timer(interval, self._timer_request_tpwr,
                                kwargs={"interval": interval})
            t.daemon = True
            t.start()
            self._log_timers["tpwr"] = t

    # ---- Resource cleanup -----------------------------------------------

    def release_resources(self) -> None:
        self._cancel_all_timers()
        if self.unit:
            self.unit.remove_unit_listener(self)
            self.unit.remove_comm_listener(self)
            # Unsubscribe optional events
            for opt, enabled in self._monitored_events.items():
                if enabled:
                    try:
                        self.unit.disable_monitor_of_event(opt)
                    except Exception:
                        pass
        super().release_resources()

    # ---- Serialization --------------------------------------------------

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["unit_name"] = self.unit.name if self.unit else ""
        return base

    @classmethod
    def from_dict(cls, data: dict,
                  unit: Optional[WistomUnit] = None) -> MonitorUnit:
        return cls(
            name=data.get("name", ""),
            log_dir=data.get("log_dir", ""),
            unit=unit,
        )
