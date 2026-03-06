"""WistomUnit — device connection state machine.

Ports the Java ``WistomUnit`` class: manages connect → login →
config-fetch → subscribe → keepalive lifecycle for a single Wistom
device.  Runs its own worker thread for state transitions.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, List, Optional, Set, Tuple,
)

from pyWNMS.events.base import WnmsEvent, Severity
from pyWNMS.events.internal import ConnectionEvent
from pyWNMS.events.wistom_event import WistomEvent
from pyWNMS.models.configuration import (
    ChannelInfo, ChannelType, IpSettings, InstalledFeatures,
    PortInfo, PortMode, Rs232Settings, TempInfo, UnitInfo,
    WistomUnitConfiguration,
)
from pyWNMS.models.data import (
    OpmChannelData, OpmChannelDataCollection,
    OpmSpectrumData, OpmTpwrData,
)

# Import the low-level client at runtime to avoid hard build dependency
# on the pyWistom package being installed in *this* interpreter; the
# caller is responsible for providing a connected WistomClient object.
try:
    from pyWistom import WistomClient
except ImportError:  # pragma: no cover
    WistomClient = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ---- Constants ----------------------------------------------------------

DEFAULT_TCP_PORT = 7734
DEFAULT_HOSTNAME = "localhost"
DEFAULT_USERNAME = "admin"


# ---- Enumerations -------------------------------------------------------

class UnitState(Enum):
    """Connection lifecycle states."""
    DISABLED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()


class OptionalEvent(Enum):
    """Subscribable alarm types beyond the mandatory System + Module."""
    OCM = 10
    OPM = 20
    NEW_CHANNEL_COUNT = 21
    TEMPERATURE = 30
    NEW_CHANNEL_FOUND = 22


# ---- Listener protocol --------------------------------------------------

class WistomUnitListener:
    """Protocol for observing unit state and configuration changes."""

    def wistom_unit_state_changed(
            self, unit: WistomUnit, cause: str = "") -> None:
        """Called when the unit transitions to a new state."""

    def wistom_unit_properties_changed(
            self, unit: WistomUnit) -> None:
        """Called when name/host/port/creds are modified."""

    def wistom_unit_configuration_changed(
            self, unit: WistomUnit) -> None:
        """Called when the cached device configuration is refreshed."""


class WistomUnitCommListener:
    """Protocol for receiving events and data from the unit."""

    def wistom_unit_comm_event_received(
            self, unit: WistomUnit, event: WnmsEvent) -> None:
        """An alarm / connection event was received."""

    def wistom_unit_comm_data_received(
            self, unit: WistomUnit, data: Any) -> None:
        """Measurement data was received (channel data, spectrum, …)."""


# ---- Data-request book-keeping ------------------------------------------

class _ApiDataRequest:
    """Pending async data request (spectrum, tpwr, channel data)."""

    __slots__ = ("receiver", "caller_ref")

    def __init__(self, receiver: WistomUnitCommListener,
                 caller_ref: Any = None) -> None:
        self.receiver = receiver
        self.caller_ref = caller_ref


# ---- WistomUnit ---------------------------------------------------------

class WistomUnit:
    """Manages a single Wistom device's connection lifecycle.

    :param name: Human-readable unit name (unique within a project).
    :param hostname: Device IP address or hostname.
    :param tcp_port: Wistom API TCP port (default 7734).
    :param username: Login username.
    :param password: Login password.
    """

    def __init__(
        self,
        name: str = "",
        hostname: str = DEFAULT_HOSTNAME,
        tcp_port: int = DEFAULT_TCP_PORT,
        username: str = DEFAULT_USERNAME,
        password: str = "",
    ) -> None:
        self.name = name
        self.hostname = hostname
        self.tcp_port = tcp_port
        self.username = username
        self.password = password

        self._state = UnitState.DISABLED
        self._triggered = False  # If True, auto-enable on project open

        # Low-level Wistom client (created dynamically on connect)
        self._client: Optional[WistomClient] = None

        # Cached device configuration
        self.configuration = WistomUnitConfiguration()

        # Event subscription ref-counts (per OptionalEvent)
        self._monitored_events: Dict[OptionalEvent, int] = {
            e: 0 for e in OptionalEvent}

        # Pending async data requests keyed by token
        self._api_data_requests: Dict[int, _ApiDataRequest] = {}
        self._request_lock = threading.Lock()

        # Listeners
        self._unit_listeners: List[WistomUnitListener] = []
        self._comm_listeners: List[WistomUnitCommListener] = []
        self._listener_lock = threading.Lock()

        # Last connection event (for UI status display)
        self._last_connection_event: Optional[WnmsEvent] = None

        # Reconnect / keepalive timers
        self._reconnect_timer: Optional[threading.Timer] = None
        self._keepalive_timer: Optional[threading.Timer] = None

        # Validate-connection interval (seconds) — set from Settings
        self._validate_connection_interval = 60.0
        self._session_timeout = 20.0
        self._connect_timeout = 5.0

        # Single worker thread for state transitions to avoid races
        self._worker_lock = threading.Lock()

    # ---- Properties / getters -------------------------------------------

    @property
    def state(self) -> UnitState:
        return self._state

    @property
    def triggered(self) -> bool:
        return self._triggered

    @triggered.setter
    def triggered(self, value: bool) -> None:
        self._triggered = value

    @property
    def last_connection_event(self) -> Optional[WnmsEvent]:
        return self._last_connection_event

    # ---- Listener management --------------------------------------------

    def add_unit_listener(self, listener: WistomUnitListener) -> None:
        with self._listener_lock:
            if listener not in self._unit_listeners:
                self._unit_listeners.append(listener)

    def remove_unit_listener(self, listener: WistomUnitListener) -> None:
        with self._listener_lock:
            try:
                self._unit_listeners.remove(listener)
            except ValueError:
                pass

    def add_comm_listener(self, listener: WistomUnitCommListener) -> None:
        with self._listener_lock:
            if listener not in self._comm_listeners:
                self._comm_listeners.append(listener)

    def remove_comm_listener(self, listener: WistomUnitCommListener) -> None:
        with self._listener_lock:
            try:
                self._comm_listeners.remove(listener)
            except ValueError:
                pass

    # ---- Fire helpers (thread-safe copy of listener list) ---------------

    def _fire_state_changed(self, cause: str = "") -> None:
        with self._listener_lock:
            listeners = list(self._unit_listeners)
        for ls in listeners:
            try:
                ls.wistom_unit_state_changed(self, cause)
            except Exception:
                logger.exception("Unit listener raised exception")

    def _fire_properties_changed(self) -> None:
        with self._listener_lock:
            listeners = list(self._unit_listeners)
        for ls in listeners:
            try:
                ls.wistom_unit_properties_changed(self)
            except Exception:
                logger.exception("Unit listener raised exception")

    def _fire_configuration_changed(self) -> None:
        with self._listener_lock:
            listeners = list(self._unit_listeners)
        for ls in listeners:
            try:
                ls.wistom_unit_configuration_changed(self)
            except Exception:
                logger.exception("Unit listener raised exception")

    def _fire_comm_event(self, event: WnmsEvent) -> None:
        with self._listener_lock:
            listeners = list(self._comm_listeners)
        for ls in listeners:
            try:
                ls.wistom_unit_comm_event_received(self, event)
            except Exception:
                logger.exception("Comm listener raised exception")

    def _fire_comm_data(self, data: Any) -> None:
        with self._listener_lock:
            listeners = list(self._comm_listeners)
        for ls in listeners:
            try:
                ls.wistom_unit_comm_data_received(self, data)
            except Exception:
                logger.exception("Comm listener raised exception")

    # ---- State machine --------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the unit.

        When enabled, the unit transitions to ``CONNECTING`` and
        begins the connection lifecycle.  When disabled, all
        resources are released.
        """
        if enabled:
            if self._state == UnitState.DISABLED:
                self._transition_to(UnitState.CONNECTING)
        else:
            self._transition_to(UnitState.DISABLED)

    def _transition_to(self, new_state: UnitState,
                       cause: str = "") -> None:
        """Execute a state transition on the worker thread."""
        def _work():
            with self._worker_lock:
                old = self._state
                self._state = new_state
                logger.info(
                    "Unit '%s': %s → %s%s",
                    self.name, old.name, new_state.name,
                    f" ({cause})" if cause else "",
                )

                conn_event: Optional[WnmsEvent] = None
                events: List[WnmsEvent] = []

                if new_state == UnitState.DISABLED:
                    conn_event, events = self._handle_state_disabled(cause)
                elif new_state == UnitState.CONNECTING:
                    conn_event, events = self._handle_state_connecting()
                elif new_state == UnitState.CONNECTED:
                    conn_event, events = self._handle_state_connected()
                elif new_state == UnitState.DISCONNECTED:
                    conn_event, events = self._handle_state_disconnected(
                        cause)

                if conn_event:
                    self._last_connection_event = conn_event
                    self._fire_comm_event(conn_event)

                for ev in events:
                    self._fire_comm_event(ev)

                self._fire_state_changed(cause)

        t = threading.Thread(target=_work, daemon=True,
                             name=f"WistomUnit-{self.name}")
        t.start()

    # ---- State handlers -------------------------------------------------

    def _handle_state_disabled(
        self, cause: str
    ) -> Tuple[Optional[ConnectionEvent], List[WnmsEvent]]:
        """Cleanup when transitioning to Disabled."""
        self._cancel_reconnect_timer()
        self._cancel_keepalive_timer()
        self._clear_data_requests()
        self._logout_and_disconnect()

        conn_event = None
        if cause:
            conn_event = ConnectionEvent(
                ConnectionEvent.OUT_BYUSER, self.username)
        return conn_event, []

    def _handle_state_connecting(
        self,
    ) -> Tuple[Optional[ConnectionEvent], List[WnmsEvent]]:
        """Attempt to connect, login, fetch config, subscribe."""
        self._cancel_reconnect_timer()

        try:
            self._client = WistomClient(
                self.hostname, self.tcp_port,
                self.username, self.password,
                threaded=True,
            )
            self._client.connection.connect()
            self._client.login()
        except (OSError, ConnectionError, TimeoutError) as exc:
            logger.warning(
                "Unit '%s': connect failed: %s", self.name, exc)
            self._state = UnitState.DISCONNECTED
            self._handle_state_disconnected(str(exc))
            return (
                ConnectionEvent(
                    ConnectionEvent.OUT_NORESPONSE, self.username),
                [],
            )
        except Exception as exc:
            # Fatal: unknown host, auth failure, etc.
            logger.error(
                "Unit '%s': fatal connect error: %s", self.name, exc)
            self._state = UnitState.DISABLED
            return (
                ConnectionEvent(
                    ConnectionEvent.OUT_UNKNOWN, self.username),
                [],
            )

        # Register alarm callback
        self._client.connection.add_alarm_listener(self._on_alarm_received)
        self._client.connection.add_connection_listener(
            self._on_connection_lost)

        # Fetch device configuration
        try:
            self._update_unit_configuration()
        except Exception as exc:
            logger.warning(
                "Unit '%s': config fetch failed: %s", self.name, exc)

        # Subscribe to mandatory + opted-in events
        events = self._subscribe_to_events()

        # Transition internally to Connected (skip worker thread)
        self._state = UnitState.CONNECTED
        self._handle_state_connected()

        conn_event = ConnectionEvent(
            ConnectionEvent.IN_USERLEVEL1, self.username)
        return conn_event, events

    def _handle_state_connected(
        self,
    ) -> Tuple[Optional[ConnectionEvent], List[WnmsEvent]]:
        """Start keepalive timer when connected."""
        self._start_keepalive_timer()
        return None, []

    def _handle_state_disconnected(
        self, cause: str = ""
    ) -> Tuple[Optional[ConnectionEvent], List[WnmsEvent]]:
        """Clean up and schedule reconnection."""
        self._cancel_keepalive_timer()
        self._clear_data_requests()
        self._logout_and_disconnect()
        self._schedule_reconnect()

        conn_event = ConnectionEvent(
            ConnectionEvent.OUT_NORESPONSE, self.username)
        return conn_event, []

    # ---- Configuration fetch sequence -----------------------------------

    def _update_unit_configuration(self) -> None:
        """Execute the 13-step configuration fetch sequence."""
        c = self._client
        if c is None:
            return

        cfg = WistomUnitConfiguration()

        # 1. SPEC SWIN — installed ports
        try:
            swin = c.get_spec_swin()
            resp = swin.get("response", {})
            for i in range(1, 17):
                key = f"port_{i}_installed"
                if resp.get(key):
                    cfg.ports[i] = PortInfo(port=i)
        except Exception as exc:
            logger.warning("Config fetch SPEC SWIN failed: %s", exc)

        # 2. SPEC SWMO — port mode
        try:
            swmo = c.get_spec_swmo()
            resp = swmo.get("response", {})
            mode_val = resp.get("mode", 0)
            mode_map = {0: PortMode.MANUAL, 1: PortMode.AUTOMATIC,
                        2: PortMode.CONFIGURED}
            cfg.port_mode = mode_map.get(mode_val, PortMode.AUTOMATIC)
            cfg.manual_port = resp.get("manual_port", 0)
        except Exception as exc:
            logger.warning("Config fetch SPEC SWMO failed: %s", exc)

        # 3. SPEC SWCO — port descriptions and priorities
        try:
            swco = c.get_spec_swco()
            resp = swco.get("response", {})
            for port_num in list(cfg.ports.keys()):
                p = cfg.ports[port_num]
                desc_key = f"port_{port_num}_description"
                prio_key = f"port_{port_num}_priority"
                desc = str(resp.get(desc_key, str(port_num))).strip()
                p.description = desc if desc else str(port_num)
                p.priority = resp.get(prio_key, 0)
        except Exception as exc:
            logger.warning("Config fetch SPEC SWCO failed: %s", exc)

        # 4. SMGR INFO — unit identity
        try:
            info = c.get_smgr_info()
            resp = info.get("response", {})
            ui = cfg.unit_info
            ui.unit_serial = resp.get("unit_serial", "")
            ui.web_serial = resp.get("sensor_serial_number", "")
            ui.web_revision = resp.get("bootstrap_revision", "")
            ui.sw_revision = resp.get("software_revision", "")
            ui.fw_revision = resp.get("firmware_revision", "")
            ui.pld_revision = resp.get("pld_revision", "")
            ui.switch_revision = resp.get("switch_software_revision", "")
        except Exception as exc:
            logger.warning("Config fetch SMGR INFO failed: %s", exc)

        # 5. SPEC CTBL — channel table
        try:
            ctbl = c.get_spec_ctbl()
            resp = ctbl.get("response", {})
            channel_ids = resp.get("channel_table", [])
            for ch_id in channel_ids:
                cfg.channels[ch_id] = ChannelInfo(channel=ch_id)
        except Exception as exc:
            logger.warning("Config fetch SPEC CTBL failed: %s", exc)

        # 6. SPEC CHNL — per-channel configuration
        for ch_id in list(cfg.channels.keys()):
            try:
                chnl = c.get_spec_chnl(ch_id)
                resp = chnl.get("response", {})
                ci = cfg.channels[ch_id]
                ci.port = resp.get("switch_port", 0)
                ci.description = str(
                    resp.get("channel_description", str(ch_id))).strip()
                if not ci.description:
                    ci.description = str(ch_id)
            except Exception as exc:
                logger.warning(
                    "Config fetch SPEC CHNL %d failed: %s", ch_id, exc)

        # 7. OPM# ENAB — OPM enabled flag
        try:
            opm_enab = c.get_opm_enable()
            resp = opm_enab.get("response", {})
            cfg.opm_enabled = bool(resp.get("toggle_enable", 0))
        except Exception as exc:
            logger.warning("Config fetch OPM ENAB failed: %s", exc)

        # 8. OPM# CHCO — OPM mode + scanning flag
        try:
            opm_chco = c.get_opm_channel_config()
            resp = opm_chco.get("response", {})
            mode_val = resp.get("process_configured_channels", 0)
            mode_map = {0: PortMode.MANUAL, 1: PortMode.AUTOMATIC,
                        2: PortMode.CONFIGURED}
            cfg.opm_mode = mode_map.get(mode_val, PortMode.AUTOMATIC)
            cfg.opm_scanning_unconfigured_channels = bool(
                resp.get("search_unconfigured_channels", 0))
        except Exception as exc:
            logger.warning("Config fetch OPM CHCO failed: %s", exc)

        # 9. OCM# ENAB — OCM enabled flag
        try:
            ocm_enab = c.get_ocm_enable()
            resp = ocm_enab.get("response", {})
            cfg.ocm_enabled = bool(resp.get("ocm_enabled", 0))
        except Exception as exc:
            logger.warning("Config fetch OCM ENAB failed: %s", exc)

        # 10. SMGR IP## — network settings
        try:
            ip = c.get_smgr_network_info()
            resp = ip.get("response", {})
            ips = cfg.ip_settings
            ips.hostname = resp.get("host_name", "")
            ips.ip_address = resp.get("ip_address", "")
            ips.subnet_mask = resp.get("subnet_mask", "")
            ips.default_gateway = resp.get("gateway_address", "")
            ips.mac_address = resp.get("mac_address", "")
        except Exception as exc:
            logger.warning("Config fetch SMGR IP## failed: %s", exc)

        # 11. SMGR SER# — RS232 settings
        try:
            ser = c.get_smgr_serial_settings()
            resp = ser.get("response", {})
            rs = cfg.rs232_settings
            rs.baudrate = resp.get("baud_rate", 0)
            rs.data_bits = resp.get("data_bits", 0)
            rs.stop_bits = resp.get("stop_bits", 0)
            rs.parity = resp.get("parity_bit", "")
        except Exception as exc:
            logger.warning("Config fetch SMGR SER# failed: %s", exc)

        # 12. SMGR TEMP — temperature info
        try:
            temp = c.get_smgr_temp()
            resp = temp.get("response", {})
            ti = cfg.temp_info
            ti.web_temp = resp.get("board_temperature", 0.0)
            ti.sensor_temp = resp.get("sensor_temperature", 0.0)
        except Exception as exc:
            logger.warning("Config fetch SMGR TEMP failed: %s", exc)

        # 13. SMGR INST — installed features
        try:
            inst = c.get_smgr_installed_features()
            resp = inst.get("response", {})
            cfg.installed_features.snmp = bool(resp.get("snmp", False))
        except Exception as exc:
            logger.warning("Config fetch SMGR INST failed: %s", exc)

        cfg.last_update = datetime.now()
        self.configuration = cfg
        self._fire_configuration_changed()
        logger.info(
            "Unit '%s': configuration updated (%d ports, %d channels)",
            self.name,
            cfg.get_no_of_installed_ports(),
            cfg.get_no_of_configured_channels(),
        )

    # ---- Event subscription ---------------------------------------------

    def _subscribe_to_events(self) -> List[WnmsEvent]:
        """Subscribe to mandatory and optional alarms, fetch existing."""
        if self._client is None:
            return []

        # Always subscribe to SystemEvent + ModuleStatus
        mandatory = [
            WnmsEvent.ID_SYSTEMEVENT,
            WnmsEvent.ID_MODULESTATUS,
        ]
        for aid in mandatory:
            try:
                self._client.subscribe_alarm(aid)
            except Exception as exc:
                logger.warning(
                    "Unit '%s': subscribe alarm %d failed: %s",
                    self.name, aid, exc)

        # Subscribe to optional events where ref-count > 0
        for opt, count in self._monitored_events.items():
            if count > 0:
                try:
                    self._client.subscribe_alarm(opt.value)
                except Exception as exc:
                    logger.warning(
                        "Unit '%s': subscribe optional %s failed: %s",
                        self.name, opt.name, exc)

        # Fetch existing alarms for all subscribed types
        all_alarm_ids = set(mandatory)
        for opt, count in self._monitored_events.items():
            if count > 0:
                all_alarm_ids.add(opt.value)

        events: List[WnmsEvent] = []
        for aid in all_alarm_ids:
            try:
                result = self._client.get_alarms(aid)
                resp = result.get("response", {})
                elements = resp.get("elements", [])
                for elem in elements:
                    sub_id = elem.get("alarm_sub_id", 0)
                    status = elem.get("status", 0)
                    ts = elem.get("timestamp", 0)
                    evts = WistomEvent.instance_of(
                        aid, sub_id, status, ts, self.configuration)
                    events.extend(evts)
            except Exception as exc:
                logger.warning(
                    "Unit '%s': fetch alarms %d failed: %s",
                    self.name, aid, exc)

        return events

    # ---- Monitored event ref-counting -----------------------------------

    def enable_monitor_of_event(self, opt: OptionalEvent) -> None:
        """Increment the reference count for an optional event type."""
        self._monitored_events[opt] = self._monitored_events.get(opt, 0) + 1
        if self._monitored_events[opt] == 1 and self._client:
            # First subscriber — subscribe on device
            try:
                self._client.subscribe_alarm(opt.value)
            except Exception as exc:
                logger.warning(
                    "Unit '%s': subscribe %s failed: %s",
                    self.name, opt.name, exc)

    def disable_monitor_of_event(self, opt: OptionalEvent) -> None:
        """Decrement the reference count for an optional event type."""
        count = self._monitored_events.get(opt, 0)
        if count <= 0:
            return
        self._monitored_events[opt] = count - 1
        if count - 1 == 0 and self._client:
            # Last subscriber gone — unsubscribe from device
            try:
                self._client.unsubscribe_alarm(opt.value)
            except Exception as exc:
                logger.warning(
                    "Unit '%s': unsubscribe %s failed: %s",
                    self.name, opt.name, exc)

    # ---- Async data requests --------------------------------------------

    def request_channel_data(
        self, receiver: WistomUnitCommListener,
        caller_ref: Any = None,
    ) -> None:
        """Request OPM channel data asynchronously."""
        if self._client is None or self._state != UnitState.CONNECTED:
            # Return empty data to caller
            empty = OpmChannelDataCollection()
            empty.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, empty)
            return
        try:
            result = self._client.get_opm_all_channels()
            data = self._build_channel_data_collection(result)
            data.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, data)
        except Exception as exc:
            logger.warning(
                "Unit '%s': channel data request failed: %s",
                self.name, exc)
            empty = OpmChannelDataCollection()
            empty.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, empty)

    def request_tpwr_data(
        self, receiver: WistomUnitCommListener,
        port_id: int, caller_ref: Any = None,
    ) -> None:
        """Request total power data for a port asynchronously."""
        if self._client is None or self._state != UnitState.CONNECTED:
            empty = OpmTpwrData(empty=True, valid=False)
            empty.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, empty)
            return
        try:
            result = self._client.get_opm_total_power(port_id)
            resp = result.get("response", {})
            data = OpmTpwrData(
                source=self.name,
                port_id=resp.get("switch_port", port_id),
                power=resp.get("power", 0.0),
                start_interval=resp.get("start_interval", 0.0),
                end_interval=resp.get("end_interval", 0.0),
            )
            data.validate_port_id(port_id)
            data.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, data)
        except Exception as exc:
            logger.warning(
                "Unit '%s': tpwr request failed: %s", self.name, exc)
            empty = OpmTpwrData(empty=True, valid=False)
            empty.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, empty)

    def request_spectrum_data(
        self, receiver: WistomUnitCommListener,
        port_id: int, caller_ref: Any = None,
    ) -> None:
        """Request frequency spectrum data for a port asynchronously."""
        if self._client is None or self._state != UnitState.CONNECTED:
            empty = OpmSpectrumData(empty=True, valid=False)
            empty.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, empty)
            return
        try:
            result = self._client.get_opm_frequency_spectrum(port_id)
            resp = result.get("response", {})
            data = OpmSpectrumData(
                source=self.name,
                port_id=resp.get("switch_port", port_id),
                power=resp.get("power_table", []),
                frequency=resp.get("frequency_table", []),
            )
            data.validate_port_id(port_id)
            data.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, data)
        except Exception as exc:
            logger.warning(
                "Unit '%s': spectrum request failed: %s", self.name, exc)
            empty = OpmSpectrumData(empty=True, valid=False)
            empty.reference = caller_ref
            receiver.wistom_unit_comm_data_received(self, empty)

    def _build_channel_data_collection(
        self, result: dict,
    ) -> OpmChannelDataCollection:
        """Convert raw ``get_opm_all_channels()`` result to data model."""
        resp = result.get("response", {})
        channels_raw = resp.get("channels", [])
        channels = []
        for ch in channels_raw:
            ocd = OpmChannelData(
                source=self.name,
                channel_id=ch.get("channel_id", 0),
                port_id=ch.get("switch_port", 0),
                central_frequency=ch.get("central_frequency", 0.0),
                fwhm=ch.get("full_width_half_maximum", 0.0),
                amplitude=ch.get("amplitude_at_central_frequency", 0.0),
                central_power=ch.get("central_power", 0.0),
                osnr=ch.get("osnr", 0.0),
                channel_spacing=ch.get("channel_spacing", 0.0),
                status_power=ch.get("central_power_status", 0),
                status_frequency=ch.get("central_frequency_status", 0),
                status_osnr=ch.get("osnr_status", 0),
                delta_power=ch.get("delta_power", 0.0),
                delta_frequency=ch.get("delta_frequency", 0.0),
                osnr_margin=ch.get("osnr_margin", 0.0),
                timestamp=ch.get("time_stamp", 0.0),
            )
            channels.append(ocd)
        col = OpmChannelDataCollection(
            source=self.name, channels=channels)
        return col

    # ---- Alarm callback (from receiver thread) --------------------------

    def _on_alarm_received(self, raw_msg: bytes) -> None:
        """Handle an alarm message pushed by the device."""
        try:
            parsed = WistomClient.parse_alarm_message(raw_msg)
            for elem in parsed.get("elements", []):
                alarm_id = elem.get("alarm_id", 0)
                sub_id = elem.get("alarm_sub_id", 0)
                status = elem.get("status", 0)
                ts = elem.get("timestamp", 0)
                events = WistomEvent.instance_of(
                    alarm_id, sub_id, status, ts, self.configuration)
                for ev in events:
                    self._fire_comm_event(ev)
        except Exception:
            logger.exception(
                "Unit '%s': failed to parse alarm message", self.name)

    def _on_connection_lost(self, connected: bool) -> None:
        """Handle connection loss detected by receiver thread."""
        if not connected and self._state == UnitState.CONNECTED:
            self._transition_to(
                UnitState.DISCONNECTED, "connection lost")

    # ---- Keepalive / reconnect ------------------------------------------

    def _start_keepalive_timer(self) -> None:
        self._cancel_keepalive_timer()
        self._keepalive_timer = threading.Timer(
            self._validate_connection_interval,
            self._keepalive_tick)
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def _cancel_keepalive_timer(self) -> None:
        if self._keepalive_timer:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None

    def _keepalive_tick(self) -> None:
        """Validate connection: send SMGR UPTI as ping."""
        if self._state == UnitState.CONNECTED and self._client:
            try:
                self._client.get_smgr_uptime()
                self._start_keepalive_timer()  # reschedule
            except Exception as exc:
                logger.warning(
                    "Unit '%s': keepalive failed: %s", self.name, exc)
                self._transition_to(
                    UnitState.DISCONNECTED, "keepalive timeout")
        elif self._state == UnitState.DISCONNECTED:
            self._transition_to(UnitState.CONNECTING)

    def _schedule_reconnect(self) -> None:
        self._cancel_reconnect_timer()
        self._reconnect_timer = threading.Timer(
            self._validate_connection_interval,
            self._reconnect_tick)
        self._reconnect_timer.daemon = True
        self._reconnect_timer.start()

    def _cancel_reconnect_timer(self) -> None:
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None

    def _reconnect_tick(self) -> None:
        if self._state == UnitState.DISCONNECTED:
            self._transition_to(UnitState.CONNECTING)

    # ---- Resource cleanup -----------------------------------------------

    def _logout_and_disconnect(self) -> None:
        """Safely logout and close the socket."""
        if self._client:
            try:
                self._client.stop_keepalive()
                self._client.unsubscribe_all_alarms()
            except Exception:
                pass
            try:
                self._client.connection.remove_alarm_listener(
                    self._on_alarm_received)
                self._client.connection.remove_connection_listener(
                    self._on_connection_lost)
            except Exception:
                pass
            try:
                self._client.connection.disconnect()
            except Exception:
                pass
            self._client = None

    def _clear_data_requests(self) -> None:
        with self._request_lock:
            self._api_data_requests.clear()

    def release_resources(self) -> None:
        """Full cleanup — disable and remove all listeners."""
        self.set_enabled(False)
        # Give the worker thread a moment to clean up
        time.sleep(0.1)
        with self._listener_lock:
            self._unit_listeners.clear()
            self._comm_listeners.clear()

    # ---- Serialization helpers ------------------------------------------

    def to_dict(self) -> dict:
        """Serialize unit properties (for project YAML)."""
        return {
            "name": self.name,
            "hostname": self.hostname,
            "tcp_port": self.tcp_port,
            "username": self.username,
            "password": self.password,
            "triggered": self._triggered,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WistomUnit:
        """Deserialize from a dictionary."""
        unit = cls(
            name=data.get("name", ""),
            hostname=data.get("hostname", DEFAULT_HOSTNAME),
            tcp_port=data.get("tcp_port", DEFAULT_TCP_PORT),
            username=data.get("username", DEFAULT_USERNAME),
            password=data.get("password", ""),
        )
        unit._triggered = data.get("triggered", False)
        return unit

    # ---- Comparison / display -------------------------------------------

    def __repr__(self) -> str:
        return (f"<WistomUnit '{self.name}' {self.hostname}:{self.tcp_port} "
                f"state={self._state.name}>")

    def __lt__(self, other: WistomUnit) -> bool:
        return self.name.lower() < other.name.lower()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WistomUnit):
            return NotImplemented
        return self.name == other.name
