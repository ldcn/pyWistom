from wistomconnection import WistomConnection
from wistomtags import (
    TAG_PARSER,
)
from wistomresponses import (
    RESPONSE_HEADER_PARSER,
    RESPONSE_PARSER,
)
from wistomconstants import (
    COMMAND_ID,
    LOGIN_RESULT,
    ERROR_CODE,
    SPECTRUM_TYPE,
    PORT_TYPE,
    ALARM_ID,
    ALARM_ELEMENT_SIZE,
    ALARM_TYPE,
    CHANNEL_STATUS,
)
import os
import socket
import struct
import logging
import threading
import cProfile
import pstats

import yaml

_SETTINGS_FILE = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "settings.yaml")

with open(_SETTINGS_FILE, "r", encoding="utf-8") as _f:
    _cfg = yaml.safe_load(_f) or {}

_device = _cfg.get("device", {})

HOST = _device.get("host", "")
PORT = _device.get("port", 7734)
USER_ID = _device.get("user_id", "")
PASSWORD = _device.get("password", "")
API_VERSION = _device.get("api_version", "API2")
SSH_HOST = _device.get("ssh_host", "") or HOST
SSH_PORT = _device.get("ssh_port", 22)


logger = logging.getLogger(__name__)

MAX_TAGS = 255


class WistomClient:
    def __init__(self, host, port, user_id, password, use_ssh=False,
                 threaded=False, api_version=None):
        self.connection = WistomConnection(
            host, port, use_ssh, user_id, password, threaded=threaded)

        self.user_id = user_id
        self.password = password
        self.api_version = api_version or API_VERSION
        self._threaded = threaded

        # Keepalive timer
        self._keepalive_timer = None
        self._keepalive_interval = 30.0  # seconds

        # Alarm subscription tracking
        self._alarm_subscriptions = {}  # alarm_id -> subscription_token
        self._next_subscription_token = 1

    def __enter__(self):
        self.connection.connect()
        self.login()
        return self

    def __exit__(self, type, value, traceback):
        self.stop_keepalive()
        self.unsubscribe_all_alarms()
        self.connection.disconnect()

    def login(self):
        """
        Authenticate with the Wistom device.

        Sends a login request using the user ID and password provided at
        client construction. The login uses the LGIN application with the
        configured API version. This is called automatically when using
        the context manager (``with`` statement).

        See API spec LGIN (100051.html).

        :returns: Raw login response bytes from the device, containing
            the login result code indicating success (user level 1-5) or
            failure reason (e.g. wrong password, user not found, max users).
        :rtype: bytes

        :raises ConnectionError: If not connected to device
        :raises TimeoutError: If device does not respond within timeout

        Example::

            >>> client = WistomClient(HOST, PORT, USER_ID, PASSWORD)
            >>> client.connection.connect()
            >>> response = client.login()
        """
        response = self.connection.login(
            self.user_id,
            self.password,
            COMMAND_ID['LOGIN'],
            b'LGIN',
            self.api_version.encode('ascii')
        )
        return response

    def __increment_token(self):
        return self.connection.increment_token()

    def __get_token(self):
        return self.connection.get_token()

    # API Commands

    def get_smgr_info(self):
        """
        Get product and calibration information from the System Manager.

        Retrieves hardware, sensor, software, and firmware identification
        strings as well as calibration frequency and temperature ranges.
        See API spec SMGR INFO (100051.html).

        :returns: Dictionary with product information:
            - ``hardware_product_number`` (str): Hardware product number
            - ``hardware_id_number`` (str): Hardware identification number
            - ``hardware_revision`` (str): Hardware revision
            - ``hardware_serial_number`` (str): Hardware serial number
            - ``sensor_product_number`` (str): Sensor product number
            - ``sensor_id_number`` (str): Sensor identification number
            - ``sensor_revision`` (str): Sensor revision
            - ``sensor_serial_number`` (str): Sensor serial number
            - ``software_product_number`` (str): Software product number
            - ``software_revision`` (str): Software revision
            - ``firmware_revision`` (str): Firmware revision
            - ``pld_revision`` (str): PLD revision
            - ``bootstrap_revision`` (str): Bootstrap revision
            - ``switch_software_revision`` (str): Switch software revision
            - ``unit_serial`` (str): Unit serial number
            - ``production_date`` (str): Production date
            - ``start_calibration_frequency`` (float): Start of calibration
              frequency range (GHz)
            - ``end_calibration_frequency`` (float): End of calibration
              frequency range (GHz)
            - ``start_calibration_temperature`` (float): Start of calibration
              temperature range (°C)
            - ``end_calibration_temperature`` (float): End of calibration
              temperature range (°C)
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     info = client.get_smgr_info()
            ...     print(info['hardware_serial_number'])
            '123456'
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'INFO',
            b''
        )

    def get_smgr_network_info(self):
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'IP##',
            b''
        )

    def get_smgr_serial_settings(self):
        self.__increment_token()
        # There is only one serial interface, 0x01,
        # but supplying the (tag number and) interface number is required.
        # If not supplied, the request will result in a GETERR.
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'SER#',
            b'\x01\x01'
        )

    def get_smgr_time(self):
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'TIME',
            b''
        )

    def get_smgr_temp(self):
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'TEMP',
            b''
        )

    def get_smgr_uptime(self):
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'UPTI',
            b''
        )

    def get_snmp_agent_listening_port(self):
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'SCFG',
            b''
        )

    def get_snmp_trap_receivers(self):
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'SLTR',
            b''
        )

    def get_wica_frqc(self):
        """
        Get frequency compensation parameters from WICA calibration.

        Retrieves the linear approximation parameters used for frequency
        compensation of the fiber optic sensor. The wavelength is computed as:
        :math:`\\lambda = k_\\lambda \\cdot t + \\lambda_0`
        where *t* is the time after the pulse start, and frequency is
        :math:`\\nu = c / \\lambda`.

        The complete compensation also includes look-up tables (see WICA LUTF).
        See API spec WICA FRQC (100051.html).

        :returns: Dictionary with frequency compensation parameters:
            - ``lambda0`` (float): Constant value in the linear wavelength
              approximation, in metres (FLOAT32)
            - ``d_lambda`` (float): Factor in the linear wavelength
              approximation, in m/s (FLOAT32)
            - ``time_to_start`` (float): Position on the fiber where the
              LUT is valid, in seconds (FLOAT64)
            - ``dtime`` (float): Time step in the LUT, in seconds (FLOAT64)
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     frqc = client.get_wica_frqc()
            ...     print(f"lambda0: {frqc['lambda0']} m")
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'WICA',
            b'FRQC',
            b''
        )

    def custom_api_request(self, command_id, app_id, op_id, data):
        self.__increment_token()
        return self.__send_request(
            command_id,
            app_id,
            op_id,
            data
        )

    def custom_api_request_raw(self, command_id, app_id, op_id, data):
        self.__increment_token()
        return self.__send_request(
            command_id,
            app_id,
            op_id,
            data
        )

    # ------------------------------------------------------------------
    # SMGR commands (additional)
    # ------------------------------------------------------------------

    def get_smgr_installed_features(self):
        """Get installed feature flags from the System Manager.

        Retrieves which optional features (e.g. SNMP) are installed on
        the device.  See API spec SMGR INST (100051.html).

        :returns: Dictionary with feature flags:
            - ``snmp`` (int): SNMP support installed (1=yes, 0=no)
            - ``obsolete`` (int): Obsolete flag
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'INST',
            b''
        )

    # ------------------------------------------------------------------
    # SPEC commands
    # ------------------------------------------------------------------

    def get_spec_swin(self):
        """Get switch port installation status.

        Retrieves which of the 16 optical switch ports are physically
        installed.  See API spec SPEC SWIN (100051.html).

        :returns: Dictionary with per-port installation flags:
            - ``port_N_installed`` (bool): True if port N is installed
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SPEC',
            b'SWIN',
            b''
        )

    def get_spec_swmo(self):
        """Get optical switch mode (automatic or manual).

        See API spec SPEC SWMO (100051.html).

        :returns: Dictionary with switch mode:
            - ``mode`` (int): 1=Automatic, other=Manual
            - ``manual_port`` (int): Active port when in manual mode
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SPEC',
            b'SWMO',
            b''
        )

    def get_spec_swco(self):
        """Get switch port configuration (priority and description).

        See API spec SPEC SWCO (100051.html).

        :returns: Dictionary with per-port config:
            - ``port_N_priority`` (int): Scan priority for port N
            - ``port_N_description`` (str): User-assigned description
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SPEC',
            b'SWCO',
            b''
        )

    def get_spec_ctbl(self):
        """Get the channel table (list of configured channel IDs).

        See API spec SPEC CTBL (100051.html).

        :returns: Dictionary with channel table:
            - ``num_channels`` (int): Number of configured channels
            - ``channel_table`` (list[int]): List of channel IDs (U16)
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SPEC',
            b'CTBL',
            b''
        )

    def get_spec_chnl(self, channel_id):
        """Get configuration for a specific channel.

        This is a parametrized GET — the channel ID is sent as tag 2
        (U16) in the request data.  See API spec SPEC CHNL (100051.html).

        :param channel_id: Channel ID to query (U16 value).
        :type channel_id: int

        :returns: Dictionary with channel configuration parameters
            including nominal frequency, thresholds, and status masks.
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device
        """
        # Tag 2 = channel_id as U16
        data = b'\x02' + struct.pack('>H', channel_id)
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SPEC',
            b'CHNL',
            data
        )

    # ------------------------------------------------------------------
    # OPM# commands
    # ------------------------------------------------------------------

    def get_opm_enable(self):
        """Get OPM enabled state.

        See API spec OPM# ENAB (100051.html).

        :returns: Dictionary with:
            - ``toggle_enable`` (int): 1=enabled, 0=disabled
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'ENAB',
            b''
        )

    def get_opm_channel_config(self):
        """Get OPM channel configuration mode.

        See API spec OPM# CHCO (100051.html).

        :returns: Dictionary with channel config mode:
            - ``process_configured_channels`` (int): 1=configured, 0=auto
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'CHCO',
            b''
        )

    def get_opm_all_channels(self):
        """Get channel data for all OPM channels.

        This is the primary monitoring query — returns frequency, power,
        OSNR, status, and spacing for every detected channel across all
        ports.  See API spec OPM# CHAL (100051.html).

        :returns: Dictionary with:
            - ``channels`` (list[dict]): Each dict contains:
                - ``channel_id`` (int), ``switch_port`` (int)
                - ``central_frequency`` (float), ``central_power`` (float)
                - ``osnr`` (float), ``channel_spacing`` (float)
                - ``central_power_status`` (int), etc.
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'CHAL',
            b''
        )

    def get_opm_channel(self, channel_id):
        """Get channel data for a specific OPM channel.

        See API spec OPM# CHNL (100051.html).

        :param channel_id: Channel ID to query (U16).
        :type channel_id: int
        :returns: Dictionary with channel measurement data.
        :rtype: dict
        """
        data = b'\x01' + struct.pack('>H', channel_id)
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'CHNL',
            data
        )

    def get_opm_total_power(self, port_id):
        """Get total optical power for a specific port.

        See API spec OPM# TPWR (100051.html).

        :param port_id: Switch port ID (U8, 1-16).
        :type port_id: int
        :returns: Dictionary with:
            - ``switch_port`` (int): Port ID
            - ``start_interval`` (float): Start frequency (GHz)
            - ``end_interval`` (float): End frequency (GHz)
            - ``power`` (float): Total power (dBm)
        :rtype: dict
        """
        data = b'\x64' + struct.pack('>B', port_id)  # tag 100 = port
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'TPWR',
            data
        )

    def get_opm_frequency_spectrum(self, port_id):
        """Get the frequency spectrum for a specific port.

        Returns arrays of frequency and power values for the full
        optical spectrum on the given port.
        See API spec OPM# FSPC (100051.html).

        :param port_id: Switch port ID (U8, 1-16).
        :type port_id: int
        :returns: Dictionary with:
            - ``switch_port`` (int): Port ID
            - ``frequency_table`` (list[float]): Frequency values (GHz)
            - ``power_table`` (list[float]): Power values (dBm)
        :rtype: dict
        """
        data = b'\x64' + struct.pack('>B', port_id)  # tag 100 = port
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'FSPC',
            data
        )

    def get_opm_averages(self):
        """Get OPM averaging configuration.

        See API spec OPM# AVRG (100051.html).

        :returns: Dictionary with:
            - ``averages`` (int): Number of spectrum averages (U32)
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'AVRG',
            b''
        )

    def get_opm_threshold(self):
        """Get OPM peak detection threshold.

        See API spec OPM# TRSH (100051.html).

        :returns: Dictionary with threshold values.
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'TRSH',
            b''
        )

    def get_opm_min_level(self):
        """Get OPM minimum detection level.

        See API spec OPM# MINL (100051.html).

        :returns: Dictionary with minimum level values.
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'MINL',
            b''
        )

    def get_opm_peak_criteria(self):
        """Get OPM peak detection criteria.

        See API spec OPM# PCRI (100051.html).

        :returns: Dictionary with peak detection parameters.
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OPM#',
            b'PCRI',
            b''
        )

    # ------------------------------------------------------------------
    # OCM# commands
    # ------------------------------------------------------------------

    def get_ocm_enable(self):
        """Get OCM enabled state.

        See API spec OCM# ENAB (100051.html).

        :returns: Dictionary with:
            - ``ocm_enabled`` (int): 1=enabled, 0=disabled
        :rtype: dict
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'OCM#',
            b'ENAB',
            b''
        )

    # ------------------------------------------------------------------
    # ALMH commands (alarm handler)
    # ------------------------------------------------------------------

    def subscribe_alarm(self, alarm_id, mode=1):
        """Subscribe to a specific alarm type.

        After subscribing, the device will push alarm messages
        asynchronously whenever the alarm condition triggers.
        Use :meth:`connection.add_alarm_listener` to receive them
        in threaded mode.

        See API spec ALMH SUBS (100051.html).

        :param alarm_id: Alarm type ID (10=OCM, 20=OPM, 21=NewChanCount,
            22=NewChanFound, 30=Temperature, 90=SystemEvent,
            91=ModuleStatus).
        :type alarm_id: int
        :param mode: Subscription mode (1=new alarms only).
        :type mode: int
        :returns: Parsed SET response (SETACK or SETNACK).
        :rtype: dict
        """
        sub_token = self._next_subscription_token
        self._next_subscription_token = (
            self._next_subscription_token + 1) & 0xFFFF

        # Build tag data: tag 1=alarm_id(U16), tag 5=mode(U8),
        # tag 6=subscription_token(U16)
        data = (
            b'\x01' + struct.pack('>H', alarm_id)
            + b'\x05' + struct.pack('>B', mode)
            + b'\x06' + struct.pack('>H', sub_token)
        )
        self.__increment_token()
        result = self.__send_set_request(b'ALMH', b'SUBS', data)
        self._alarm_subscriptions[alarm_id] = sub_token
        return result

    def unsubscribe_alarm(self, alarm_id):
        """Unsubscribe from a specific alarm type.

        See API spec ALMH UNSU (100051.html).

        :param alarm_id: Alarm type ID to unsubscribe from.
        :type alarm_id: int
        :returns: Parsed SET response.
        :rtype: dict
        """
        sub_token = self._alarm_subscriptions.pop(alarm_id, None)
        if sub_token is None:
            return {"response": {"error": "Not subscribed to alarm"}}

        data = b'\x06' + struct.pack('>H', sub_token)
        self.__increment_token()
        return self.__send_set_request(b'ALMH', b'UNSU', data)

    def subscribe_all_alarms(self):
        """Subscribe to all 7 alarm types used by WNMS.

        :returns: Dictionary mapping alarm_id to subscribe result.
        :rtype: dict
        """
        results = {}
        for alarm_id in ALARM_TYPE:
            results[alarm_id] = self.subscribe_alarm(alarm_id)
        return results

    def unsubscribe_all_alarms(self):
        """Unsubscribe from all currently subscribed alarm types."""
        for alarm_id in list(self._alarm_subscriptions.keys()):
            try:
                self.unsubscribe_alarm(alarm_id)
            except Exception:
                logger.debug("Failed to unsubscribe alarm %d", alarm_id)

    def get_alarms(self, alarm_id):
        """Fetch current active alarms of a specific type.

        This is a parametrized GET that retrieves alarmed elements
        without subscribing.  See API spec ALMH ALRM (100051.html).

        :param alarm_id: Alarm type ID to query.
        :type alarm_id: int
        :returns: Dictionary with alarm records.
        :rtype: dict
        """
        data = b'\x01' + struct.pack('>H', alarm_id)
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'ALMH',
            b'ALRM',
            data
        )

    # ------------------------------------------------------------------
    # Keepalive
    # ------------------------------------------------------------------

    def start_keepalive(self, interval=30.0):
        """Start periodic keepalive pings using SMGR UPTI.

        :param interval: Seconds between pings (default 30).
        :type interval: float
        """
        self._keepalive_interval = interval
        self._schedule_keepalive()

    def stop_keepalive(self):
        """Stop the keepalive timer."""
        if self._keepalive_timer:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None

    def _schedule_keepalive(self):
        self._keepalive_timer = threading.Timer(
            self._keepalive_interval, self._keepalive_ping)
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def _keepalive_ping(self):
        try:
            self.get_smgr_uptime()
            logger.debug("Keepalive ping successful")
        except Exception as exc:
            logger.warning("Keepalive ping failed: %s", exc)
        finally:
            if self.connection.socket:
                self._schedule_keepalive()

    ##################
    # Private methods

    # Helper methods
    def __send_request(self, cid, app_id, op_id, request_data, timeout=5.0):
        data_length = len(request_data)
        token = self.connection.get_token()
        payload = (cid
                   + token.to_bytes(2, 'big')
                   + app_id
                   + op_id
                   + data_length.to_bytes(4, 'big')
                   + request_data)
        if not self.connection.socket:
            raise ConnectionError("Not connected to server")

        if self._threaded and self.connection._running:
            # Threaded mode: use token-based correlation
            try:
                response = self.connection.send_and_receive(
                    payload, token, timeout=timeout)
            except TimeoutError:
                raise TimeoutError(
                    f"Request timed out after {timeout} seconds")
        else:
            # Synchronous mode: direct socket I/O (original behavior)
            self.connection.socket.settimeout(timeout)
            try:
                self.connection.socket.sendall(payload)
                response = self.__receive_full_response()
            except socket.timeout:
                raise TimeoutError(
                    f"Request timed out after {timeout} seconds")
            finally:
                self.connection.socket.settimeout(None)

        return self.__handle_response(app_id, op_id, response, request_data)

    def __send_set_request(self, app_id, op_id, request_data, timeout=5.0):
        """Send a SET command and return the parsed response.

        SET commands use command ID ``SET`` (0x0003) and expect either
        ``SETACK`` or ``SETNACK`` in return.
        """
        return self.__send_request(
            COMMAND_ID['SET'], app_id, op_id, request_data, timeout=timeout)

    def __receive_full_response(self):
        # Read the header first to determine the total payload size
        header = self.connection.socket.recv(16)
        if len(header) < 16:
            raise ConnectionError("Incomplete response header received")

        data_length = int.from_bytes(header[12:16], 'big')
        total_length = 16 + data_length

        # Receive the remaining payload in chunks
        response = header
        while len(response) < total_length:
            chunk = self.connection.socket.recv(
                min(4096, total_length - len(response)))
            if not chunk:
                raise ConnectionError(
                    "Connection closed before full payload was received")
            response += chunk

        return response

    def __handle_response(self, app_id, op_id, response, request_data=None):
        cid = response[0:2]
        header_parser_name = RESPONSE_HEADER_PARSER.get(
            cid, "__parse_unknown_command")
        header_parser = getattr(self, header_parser_name,
                                self.__parse_unknown_command)
        parsed_header = header_parser(response)

        if cid == COMMAND_ID["GETRES"] or cid == COMMAND_ID["LOGINRES"]:
            parser_name = RESPONSE_PARSER.get(app_id.decode('ascii'), {}).get(
                op_id.decode('ascii'), "_parse_unknown_response")
            parser = getattr(self, parser_name, self.__parse_unknown_response)

            # Ensure data is only passed if required by the parser
            if request_data and callable(parser):
                parsed_response = parser(response, request_data)
            else:
                parsed_response = parser(response)

            return {
                "header": parsed_header,
                "response": parsed_response,
            }
        elif cid == COMMAND_ID["SETACK"]:
            return {
                "header": parsed_header,
                "response": {"acknowledged": True},
            }
        elif cid == COMMAND_ID["SETNACK"] or cid == COMMAND_ID["GETERR"]:
            return {
                "header": parsed_header,
                "response": {"error": True},
            }
        else:
            return parsed_header

    def __parse_unknown_command(self, response):
        print(f"Unknown command: {response[0:2].hex()}")
        header = {"cid": response[0:2].hex(),
                  "token": int.from_bytes(response[2:4], 'big'),
                  "app_id": response[4:8].decode('ascii'),
                  "op_id": response[8:12].decode('ascii'),
                  "data_length": int.from_bytes(response[12:16], 'big'),
                  }
        return {
            "header": header,
            "response": self.__parse_unknown_response(response),
        }

    def __parse_unknown_response(self, response, data=None):
        return {
            "bytes": response[16:],
            "hex": response[16:].hex(),
        }

    def _parse_loginres_header(self, response):
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')

        return {
            "Login result": f"{app_id} {op_id}",
            "Token": f"{token}",
        }

    def _parse_setack_header(self, response):
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')

        return {
            "SET Acknowledged": f"{app_id} {op_id}",
            "Token": f"{token}",
        }

    def _parse_setnack_header(self, response):
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')
        error_code = response[-2:]
        tag_number = response[-4:-2]

        return {
            "SET Not acknowledged": f"{app_id} {op_id}",
            "Token": f"{token}",
            "Error code": ERROR_CODE[error_code],
            "Tag number": int.from_bytes(tag_number, 'big')
            if tag_number != b'\x00\x00' else None
        }

    def _parse_geterr_header(self, response):
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')
        error_code = response[-2:]
        tag_number = response[-4:-2]

        return {
            "GET Error": f"{app_id} {op_id}",
            "Token": f"{token}",
            "Error code": ERROR_CODE[error_code],
            "Tag number": int.from_bytes(tag_number, 'big')
            if tag_number != b'\x00\x00' else None
        }

    def _parse_getres_header(self, response):
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')
        data_length = int.from_bytes(response[12:16], 'big')
        data_length_measured = (len(response[16:]))
        return {
            "GET Response": f"{app_id} {op_id}",
            "Token": f"{token}",
            "data_length": f"{data_length}",
            "data_length_measured": f"{data_length_measured}"
        }

    # Parses the login response into a human-readable format
    def _parse_apiv2_login_response(self, response):
        command_id = response[0:2]
        login_result = response[-4:]
        command_name = next((key for key, value in COMMAND_ID.items(
        ) if value == command_id), "Unknown Command")
        login_result_name = next((key for key, value in LOGIN_RESULT.items(
        ) if value == login_result), "Unknown Login Result")

        return {
            "command_id": command_name,
            "login_result": login_result_name
        }

    ###################################################################
    # Parsers for getRes responses
    # For reference, see Wistom API documentation (document 100051)
    ###################################################################

    def _parse_login_user_info_response(self, response, data=None):
        user_info = {}
        index = 16
        payload = response[index:]

        while index < len(payload):
            tag = payload[index]
            index += 1
            tag_name = TAG_PARSER.get('LGIN', {}).get(
                'UINF', {}).get(tag, f"unknown_tag_{tag}")

            # Find the null byte and slice the string directly
            null_terminated_string_end = payload.find(b'\x00', index)
            if (null_terminated_string_end == -1):
                break
            user_name = payload[:null_terminated_string_end].decode('ascii')
            user_info[tag_name] = user_name
            index += (null_terminated_string_end - index + 1)
            tag = payload[index]
            tag_name = TAG_PARSER.get('LGIN', {}).get(
                'UINF', {}).get(tag, f"unknown_tag_{tag}")
            user_level = struct.unpack('>I', payload[index:index + 4])[0]
            user_info[tag_name] = user_level
            print(user_info)

        return user_info

    def _parse_login_session_info_response(self, response, data=None):
        session_info = {}
        number_of_users = 0
        index = 16

        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('LGIN', {}).get('SINF', {}).get(
                tag, f"unknown_tag_{tag}") + f"_{number_of_users}"
            if tag == 1:
                string_end = response.find(b'\x00', index)
                if string_end == -1:
                    break
                session_info[tag_name] = response[index:string_end].decode(
                    'ascii')
                index += (string_end - index + 1)
            elif tag == 5:
                session_info[tag_name] = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
            number_of_users += 1

        return session_info

    def _parse_serial_response(self, response, data=None):
        serial_settings = {}
        index = 16
        # If data is not provided, use an empty byte string
        data = data or b''
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'SER#', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 2:
                serial_settings[tag_name] = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
            else:
                serial_settings[tag_name] = struct.unpack(
                    'B', response[index:index + 1])[0]
                index += 1

        return serial_settings

    def _parse_network_info_response(self, response):
        network_info = {}
        index = 16

        while index < len(response):
            tag = response[index]
            if tag == 6:
                break
            else:
                index += 1
                tag_name = TAG_PARSER.get('SMGR', {}).get(
                    'IP##', {}).get(tag, f"unknown_tag_{tag}")
                string_end = response.find(b'\x00', index)
                if string_end == -1:
                    break
                network_info[tag_name] = response[index:string_end].decode(
                    'ascii')
                index = string_end + 1

        tag = response[index]
        index += 1
        tag_name = TAG_PARSER.get('SMGR', {}).get(
            'IP##', {}).get(tag, f"unknown_tag_{tag}")
        network_info[tag_name] = struct.unpack(
            '>H', response[index:index + 2])[0]

        return network_info

    def _parse_datetime_response(self, response):
        date_time = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'TIME', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 1:
                date_time[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            else:
                date_time[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1

        return date_time

    def _parse_product_info_response(self, response):
        product_info = {}
        strings = response[16:].split(b'\x00', 16)[:-1]
        for string in range(len(strings)):
            tag = strings[string][0]
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'INFO', {}).get(tag, f"unknown_tag_{tag}")
            product_info[tag_name] = strings[string][1:].decode('ascii')

        # +1 for each null character and +1 for each tag
        index = sum((len(s) + 2) for s in strings[:16])
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'INFO', {}).get(tag, f"unknown_tag_{tag}")
            if tag < 82:
                product_info[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            else:
                product_info[tag_name] = struct.unpack(
                    '>f', response[index:index + 4])[0]
                index += 4

        return product_info

    def _parse_system_uptime_response(self, response):
        """
        Parses the system uptime response.
        :param response: The raw response from the system uptime command.
        :return: A dictionary containing the parsed uptime information.
        """
        system_uptime = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'UPTI', {}).get(tag, f"unknown_tag_{tag}")
            system_uptime[tag_name] = struct.unpack(
                '>f', response[index:index + 4])[0]
            index += 4

        return system_uptime

    def _parse_system_temperature_response(self, response):
        system_temperature = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'TEMP', {}).get(tag, f"unknown_tag_{tag}")
            system_temperature[tag_name] = struct.unpack(
                '>f', response[index:index + 4])[0]
            index += 4

        return system_temperature

    def _parse_list_snmp_trap_receivers_response(self, response):
        trap_receivers = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'SLTR', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 1:
                # The first tag is a null-terminated string for the IP address
                string_end = response.find(b'\x00', index)
                if string_end == -1:
                    break
                trap_receivers[tag_name] = response[index:string_end].decode(
                    'ascii')
                index = string_end + 1
            elif tag == 2:
                # The second tag is a 2-byte integer for the port number
                trap_receivers[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            else:
                # For any other tags,
                # just read the raw value as bytes (length 1)
                trap_receivers[tag_name] = response[index:index + 1]
                index += 1

        return trap_receivers

    def _parse_snmp_config_response(self, response):
        snmp_config = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'SCFG', {}).get(tag, f"unknown_tag_{tag}")
            snmp_config[tag_name] = struct.unpack(
                '>H', response[index:index + 2])[0]
            index += 2

        return snmp_config

    def _parse_smgr_inst_response(self, response):
        index = 16
        installed_features = {}
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get(
                'INST', {}).get(tag, f"unknown_tag_{tag}")
            installed_features[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1

        return installed_features

    ###################################################################
    # SPEC (Spectrum parameter) API function parsers
    ###################################################################

    def _parse_spec_swin_response(self, response, data=None):
        """Parse SPEC SWIN response — switch port installation status.

        Tags 1-50 are U8 boolean flags (1=installed, 0=not installed).
        """
        installed = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SPEC', {}).get(
                'SWIN', {}).get(tag, f"unknown_tag_{tag}")
            if tag <= 50:
                installed[tag_name] = bool(response[index])
                index += 1
            elif 101 <= tag <= 104:
                # Variable-length U8 array
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                values = list(response[index:index + count])
                index += count
                installed[tag_name] = values
            else:
                break
        return installed

    def _parse_spec_swmo_response(self, response, data=None):
        """Parse SPEC SWMO response — switch mode (auto/manual)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SPEC', {}).get(
                'SWMO', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack('>B', response[index:index+1])[0]
            index += 1
        return result

    def _parse_spec_swco_response(self, response, data=None):
        """Parse SPEC SWCO response — switch port config.

        Tags 1-16: U8 priority.  Tags 51-66: null-terminated strings
        (description).  Tags 101-116: U8 config.  Tags 151-166: F32.
        """
        config = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SPEC', {}).get(
                'SWCO', {}).get(tag, f"unknown_tag_{tag}")
            if 1 <= tag <= 16 or 101 <= tag <= 116:
                config[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif 51 <= tag <= 66:
                string_end = response.find(b'\x00', index)
                if string_end == -1:
                    break
                config[tag_name] = response[index:string_end].decode(
                    'ascii', errors='replace')
                index = string_end + 1
            elif 151 <= tag <= 166:
                config[tag_name] = struct.unpack(
                    '>f', response[index:index + 4])[0]
                index += 4
            else:
                break
        return config

    def _parse_spec_ctbl_response(self, response, data=None):
        """Parse SPEC CTBL response — channel table.

        Tag 1: U16 channel count.  Tag 2: variable-length U16 array
        (channel IDs).
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            if tag == 1:
                result["num_channels"] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            elif tag == 2:
                # Variable-length U16 array: U32 count + N×U16
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                channels = []
                for _ in range(count):
                    channels.append(
                        struct.unpack('>H', response[index:index + 2])[0])
                    index += 2
                result["channel_table"] = channels
            else:
                break
        return result

    def _parse_spec_chnl_response(self, response, data=None):
        """Parse SPEC CHNL response — per-channel configuration.

        Contains a mix of tag types: U32 fixed array (tag 1), U16, U8,
        F64, and null-terminated strings.
        """
        channel = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SPEC', {}).get(
                'CHNL', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 1:
                # Fixed-size array of 32 U32 values (channel_id_map)
                values = []
                for _ in range(32):
                    values.append(
                        struct.unpack('>I', response[index:index + 4])[0])
                    index += 4
                channel[tag_name] = values
            elif tag == 2:
                channel[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            elif tag == 3:
                # activate_mask: U16
                channel[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            elif tag == 100:
                # switch_port: U8
                channel[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag == 27:
                # channel_description: null-terminated string
                string_end = response.find(b'\x00', index)
                if string_end == -1:
                    break
                channel[tag_name] = response[index:string_end].decode(
                    'ascii', errors='replace')
                index = string_end + 1
            elif 4 <= tag <= 26:
                # All other channel params are F64
                channel[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            else:
                break
        return channel

    ###################################################################
    # OPM# (Optical Performance Monitor) API function parsers
    ###################################################################

    def _parse_opm_enable_response(self, response, data=None):
        """Parse OPM# ENAB response — OPM enabled flag (U8)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'ENAB', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1
        return result

    def _parse_opm_channel_config_response(self, response, data=None):
        """Parse OPM# CHCO response — channel config mode.

        Tag types: 1=U8, 2=U8, 3=F64, 4=U8, 5=U16.
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'CHCO', {}).get(tag, f"unknown_tag_{tag}")
            if tag in (1, 2, 4):
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag == 3:
                result[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            elif tag == 5:
                result[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            else:
                break
        return result

    def _parse_opm_channel_data(self, response, app_id, op_id):
        """Shared parser for OPM# CHNL and CHAL responses.

        Multi-channel format: each occurrence of tag 1 (channel_id)
        begins a new channel record.  Tags: 1=U16, 100=U8,
        2/4/5/6/7/8/12/13/14=F64, 9/10/11=U8, 29=F32.
        """
        channels = []
        current = None
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                op_id, {}).get(tag, f"unknown_tag_{tag}")

            if tag == 1:
                # Start of a new channel record
                if current is not None:
                    channels.append(current)
                current = {}
                current[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            elif tag == 100:
                if current is not None:
                    current[tag_name] = struct.unpack(
                        '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (9, 10, 11):
                if current is not None:
                    current[tag_name] = struct.unpack(
                        '>B', response[index:index + 1])[0]
                index += 1
            elif tag == 29:
                if current is not None:
                    current[tag_name] = struct.unpack(
                        '>f', response[index:index + 4])[0]
                index += 4
            elif tag in (2, 3, 4, 5, 6, 7, 8, 12, 13, 14):
                if current is not None:
                    current[tag_name] = struct.unpack(
                        '>d', response[index:index + 8])[0]
                index += 8
            else:
                # Unknown tag — try to skip as F64 (most common)
                logger.debug("OPM# %s: unknown tag %d at index %d",
                             op_id, tag, index - 1)
                break

        if current is not None:
            channels.append(current)
        return {"channels": channels}

    def _parse_opm_channel_status_response(self, response, data=None):
        """Parse OPM# CHNL response (single channel status)."""
        return self._parse_opm_channel_data(response, 'OPM#', 'CHNL')

    def _parse_opm_all_channels_status_response(self, response, data=None):
        """Parse OPM# CHAL response (all channels data)."""
        return self._parse_opm_channel_data(response, 'OPM#', 'CHAL')

    def _parse_opm_total_power_response(self, response, data=None):
        """Parse OPM# TPWR response.

        Tags: 100=U8(port), 1/2/3=F64 (start/end/power).
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'TPWR', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 100:
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (1, 2, 3):
                result[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            else:
                break
        return result

    def _parse_opm_frequency_spectrum_response(self, response, data=None):
        """Parse OPM# FSPC response.

        Tags: 100=U8(port), 3=F32*0(freq array), 4=F32*0(power array).
        Variable-length arrays are prefixed with U32 count.
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'FSPC', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 100:
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (3, 4):
                # Variable-length F32 array
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                values = []
                for _ in range(count):
                    values.append(struct.unpack(
                        '>f', response[index:index + 4])[0])
                    index += 4
                result[tag_name] = values
            else:
                break
        return result

    def _parse_opm_wavelength_spectrum_response(self, response, data=None):
        """Parse OPM# WSPC response.

        Tags: 100=U8(port), 5=F32*0(wavelength array),
        4=F32*0(power array).
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'WSPC', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 100:
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (4, 5):
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                values = []
                for _ in range(count):
                    values.append(struct.unpack(
                        '>f', response[index:index + 4])[0])
                    index += 4
                result[tag_name] = values
            else:
                break
        return result

    def _parse_opm_compact_spectrum_response(self, response, data=None):
        """Parse OPM# CSPC response.

        Tags: 100=U8(port), 101/102/103=U8, 40/50=F32*0,
        51=F32(scalar).
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'CSPC', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 100 or tag in (101, 102, 103):
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (40, 50):
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                values = []
                for _ in range(count):
                    values.append(struct.unpack(
                        '>f', response[index:index + 4])[0])
                    index += 4
                result[tag_name] = values
            elif tag == 51:
                result[tag_name] = struct.unpack(
                    '>f', response[index:index + 4])[0]
                index += 4
            else:
                break
        return result

    def _parse_opm_averages_response(self, response, data=None):
        """Parse OPM# AVRG response — averages count (U32)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'AVRG', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>I', response[index:index + 4])[0]
            index += 4
        return result

    def _parse_opm_power_calc_response(self, response, data=None):
        """Parse OPM# CALC response — power calculation toggle (U8)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'CALC', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1
        return result

    def _parse_opm_config_response(self, response, data=None):
        """Parse OPM# CNFG response.

        Tags: 1=U8, 2/3=U16, 4=U8.
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'CNFG', {}).get(tag, f"unknown_tag_{tag}")
            if tag in (1, 4):
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (2, 3):
                result[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            else:
                break
        return result

    def _parse_opm_osnr_config_response(self, response, data=None):
        """Parse OPM# OSNR response.

        Tags: 1=U8, 2/3/4/5=F64, 6=U32.
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'OSNR', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 1:
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (2, 3, 4, 5):
                result[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            elif tag == 6:
                result[tag_name] = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
            else:
                break
        return result

    def _parse_opm_frequency_option_response(self, response, data=None):
        """Parse OPM# FRQO response — frequency calc mode (U8)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'FRQO', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1
        return result

    def _parse_opm_output_spectrum_response(self, response, data=None):
        """Parse OPM# OUTP response.

        Tags 1 and 2 are variable-length F32 arrays.
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'OUTP', {}).get(tag, f"unknown_tag_{tag}")
            if tag in (1, 2):
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                values = []
                for _ in range(count):
                    values.append(struct.unpack(
                        '>f', response[index:index + 4])[0])
                    index += 4
                result[tag_name] = values
            else:
                break
        return result

    def _parse_opm_raw_data_response(self, response, data=None):
        """Parse OPM# RAWD response.

        Tag 1: variable-length F32 array (spectrum).  Tag 100: U8 (port).
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'RAWD', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 1:
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                values = []
                for _ in range(count):
                    values.append(struct.unpack(
                        '>f', response[index:index + 4])[0])
                    index += 4
                result[tag_name] = values
            elif tag == 100:
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            else:
                break
        return result

    def _parse_opm_time_spectrum_response(self, response, data=None):
        """Parse OPM# TSPC response.

        Tags 2/4: variable-length F32 arrays.  Tag 100: U8 (port).
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'TSPC', {}).get(tag, f"unknown_tag_{tag}")
            if tag in (2, 4):
                count = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                values = []
                for _ in range(count):
                    values.append(struct.unpack(
                        '>f', response[index:index + 4])[0])
                    index += 4
                result[tag_name] = values
            elif tag == 100:
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            else:
                break
        return result

    def _parse_opm_threshold_response(self, response, data=None):
        """Parse OPM# TRSH response.

        Tags: 1/2=F64, 3=U16.
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'TRSH', {}).get(tag, f"unknown_tag_{tag}")
            if tag in (1, 2):
                result[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            elif tag == 3:
                result[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            else:
                break
        return result

    def _parse_opm_min_level_response(self, response, data=None):
        """Parse OPM# MINL response — both tags are F64."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'MINL', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>d', response[index:index + 8])[0]
            index += 8
        return result

    def _parse_opm_peak_criteria_response(self, response, data=None):
        """Parse OPM# PCRI response.

        Tags: 1/2/4/5=F64, 6=U8.
        """
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'PCRI', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 6:
                result[tag_name] = struct.unpack(
                    '>B', response[index:index + 1])[0]
                index += 1
            elif tag in (1, 2, 4, 5):
                result[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            else:
                break
        return result

    def _parse_opm_filter_width_response(self, response, data=None):
        """Parse OPM# FILW response — filter width (F64)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'FILW', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>d', response[index:index + 8])[0]
            index += 8
        return result

    def _parse_opm_switch_handling_response(self, response, data=None):
        """Parse OPM# SWHA response — spectrum port (U8)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OPM#', {}).get(
                'SWHA', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1
        return result

    ###################################################################
    # OCM# (Optical Channel Monitor) API function parsers
    ###################################################################

    def _parse_ocm_enable_response(self, response, data=None):
        """Parse OCM# ENAB response — OCM enabled flag (U8)."""
        result = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('OCM#', {}).get(
                'ENAB', {}).get(tag, f"unknown_tag_{tag}")
            result[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1
        return result

    ###################################################################
    # ALMH (Alarm Handler) API function parsers
    ###################################################################

    def _parse_almh_alrm_response(self, response, data=None):
        """Parse ALMH ALRM GET response — current active alarms.

        Multi-record format: each tag 1 (alarm_id) starts a new record.
        Tags: 1/2/7=U16, 3=U32, 4/5/6=U32 (timestamps).
        """
        alarms = []
        current = None
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('ALMH', {}).get(
                'ALRM', {}).get(tag, f"unknown_tag_{tag}")

            if tag == 1:
                if current is not None:
                    alarms.append(current)
                current = {}
                current[tag_name] = struct.unpack(
                    '>H', response[index:index + 2])[0]
                index += 2
            elif tag == 2:
                if current is not None:
                    current[tag_name] = struct.unpack(
                        '>H', response[index:index + 2])[0]
                index += 2
            elif tag in (3, 4, 5, 6):
                if current is not None:
                    current[tag_name] = struct.unpack(
                        '>I', response[index:index + 4])[0]
                index += 4
            elif tag == 7:
                if current is not None:
                    current[tag_name] = struct.unpack(
                        '>H', response[index:index + 2])[0]
                index += 2
            else:
                break

        if current is not None:
            alarms.append(current)
        return {"alarms": alarms}

    ###################################################################
    # Alarm message parser (for unsolicited alarm push messages)
    ###################################################################

    @staticmethod
    def parse_alarm_message(raw_msg):
        """Parse a raw alarm message from the receiver thread.

        Alarm messages have a different header: cmd_id(2) + token(2) +
        data_size(4) = 8 bytes, followed by alarm elements.

        :param raw_msg: Raw alarm message bytes.
        :type raw_msg: bytes
        :returns: Dictionary with:
            - ``cmd_id`` (str): Hex command ID
            - ``token`` (int): Message token
            - ``elements`` (list[dict]): Alarm elements, each with
              ``alarm_id``, ``alarm_sub_id``, ``status``, and optionally
              ``timestamp`` and ``extended_info``.
        :rtype: dict
        """
        cmd_id = raw_msg[0:2]
        token = struct.unpack('>H', raw_msg[2:4])[0]
        data_size = struct.unpack('>I', raw_msg[4:8])[0]

        element_size = ALARM_ELEMENT_SIZE.get(cmd_id, 8)
        payload = raw_msg[8:]
        num_elements = len(payload) // element_size

        elements = []
        offset = 0
        for _ in range(num_elements):
            alarm_id = struct.unpack('>H', payload[offset:offset + 2])[0]
            alarm_sub_id = struct.unpack(
                '>H', payload[offset + 2:offset + 4])[0]
            status = struct.unpack('>I', payload[offset + 4:offset + 8])[0]

            elem = {
                "alarm_id": alarm_id,
                "alarm_sub_id": alarm_sub_id,
                "status": status,
                "alarm_type": ALARM_TYPE.get(alarm_id, f"Unknown({alarm_id})"),
            }

            if element_size >= 12:
                elem["timestamp"] = struct.unpack(
                    '>I', payload[offset + 8:offset + 12])[0]
            if element_size >= 14:
                elem["extended_info"] = struct.unpack(
                    '>H', payload[offset + 12:offset + 14])[0]

            elements.append(elem)
            offset += element_size

        return {
            "cmd_id": cmd_id.hex(),
            "token": token,
            "elements": elements,
        }

    def _parse_frequency_regulator_values(self, response):
        index = 16
        frequency_regulator_values = {}
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('PULF', {}).get(
                'REGV', {}).get(tag, f"unknown_tag_{tag}")
            frequency_regulator_values[tag_name] = struct.unpack(
                '>d', response[index:index + 8])[0]
            index += 8
        return frequency_regulator_values

    # ------------------------------------------------------------------
    # WICA (Wistom Calibration) API function parsers
    # For reference, see Wistom API documentation (document 100051)
    # ------------------------------------------------------------------

    def _parse_wica_frqc_response(self, response, data=None):
        """
        Parse the WICA FRQC (frequency compensation) response.

        Tags 1-2 are FLOAT32 (4 bytes), tags 3-4 are FLOAT64 (8 bytes).

        :param response: Raw response bytes from the WICA FRQC command.
        :param data: Optional data parameter (unused).
        :returns: Dictionary with frequency compensation parameters.
        :rtype: dict
        """
        frqc = {}
        index = 16  # Skip header
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WICA', {}).get(
                'FRQC', {}).get(tag, f"unknown_tag_{tag}")
            if tag in (1, 2):  # FLOAT32
                frqc[tag_name] = struct.unpack(
                    '>f', response[index:index + 4])[0]
                index += 4
            elif tag in (3, 4):  # FLOAT64
                frqc[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8
            else:
                break  # Unknown tag, stop parsing
        return frqc

    # ------------------------------------------------------------------
    # Wistsense API function parsers
    # For reference, see Wistom API documentation (document 100051)
    # ------------------------------------------------------------------

    def _parse_wsns_data(self, response, data=None):  # TODO Fix this function
        """
        Parses the WSNS DATA response.
        :param response: The raw response from the WSNS DATA command.
        :param data: Optional data parameter, not used in this implementation.
        :return: A dictionary containing the parsed spectrum data.
        """
        spectrum_data = {}
        index = 16
        if data is None:
            while index < len(response):
                tag = response[index]
                index += 1
                tag_name = TAG_PARSER.get('WSNS', {}).get(
                    'DATA', {}).get(tag, f"unknown_tag_{tag}")
                value = response[index]
                spectrum_data[tag_name] = bool(value)
                index += 1
            return spectrum_data
        if data[0] == 0x0a:  # 0x0a (10) is the GET tag for spectrum type
            # The value entered after the 0x0a tag can be any value
            # data[1] == 0 does the same as data == None
            # data[1] in {1, 2, 3, 4, 5} is documented as spectrum type
            # data[1] == 6 is also used but is not documented
            # data[1] > 6 will return the same data as data[1] == 1
            if data[1] in {1, 2, 3, 4, 5, 6}:
                spectrum_data_values = []
                tag = response[index]
                index += 1
                spectrum_type = SPECTRUM_TYPE.get(data[1], "Unknown")
                tag_name = TAG_PARSER.get('WSNS', {}).get(
                    'DATA', {}).get(tag, f"unknown_tag_{tag}")
                spectrum_data_length = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
                for _ in range(spectrum_data_length):
                    spectrum_value = struct.unpack(
                        '>f', response[index:index + 4])[0]
                    spectrum_data_values.append(spectrum_value)
                    index += 4
                spectrum_data = {
                    "spectrum_type": spectrum_type,
                    "spectrum_data_length": spectrum_data_length,
                    "spectrum_data_values": spectrum_data_values,
                }
            return spectrum_data

    def _parse_wsns_port(self, response):
        sensor_ports = {}
        index = 16  # start after header
        while index < len(response):
            port_tag = response[index]
            index += 1

            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PORT', {}).get(port_tag, f'unknown_port_{port_tag}')
            type_name = PORT_TYPE.get(response[index], "Unknown")
            sensor_ports[tag_name] = type_name
            index += 1

        return sensor_ports

    def _parse_wsns_next(self, response):
        peak_frequencies_ports = {}
        peak_widths_ports = {}
        peak_amplitudes_ports = {}
        index = 16  # Start after header

        # Tag 101-116 (Frequency of each peak in spectrum, per port)
        # Tag 151-166 (FWHM of each peak)
        # Tag 201-216 (Amplitudes of each peak)
        # First value after each tag is the number of peaks.

        while index < len(response):
            port_tag = response[index]
            # Tag 7, 3, 4, 5, 6 comes after peak data in this order
            # and is parsed differently
            if port_tag == 7:
                break
            index += 1

            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(port_tag, f"unknown_tag_{port_tag}")

            # Handle peak widths (151-166)
            if 151 <= port_tag <= 166:
                number_of_peak_widths = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
                peak_widths = []
                for _ in range(number_of_peak_widths):
                    peak_width = struct.unpack(
                        '>d', response[index:index + 8])[0]
                    peak_widths.append(peak_width)
                    index += 8
                peak_widths_ports[tag_name] = {
                    "number_of_peaks": number_of_peak_widths,
                    "peak_widths": peak_widths,
                }
                continue

            # Handle peak amplitudes (201-216)
            if 201 <= port_tag <= 216:
                number_of_peak_amplitudes = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
                peak_amplitudes = []
                for _ in range(number_of_peak_amplitudes):
                    peak_amplitude = struct.unpack(
                        '>d', response[index:index + 8])[0]
                    peak_amplitudes.append(peak_amplitude)
                    index += 8
                peak_amplitudes_ports[tag_name] = {
                    "number_of_peaks": number_of_peak_amplitudes,
                    "peak_amplitudes": peak_amplitudes,
                }
                continue

            # Read the number of peaks (UINT32)
            number_of_frequency_peaks = struct.unpack(
                '>I', response[index:index + 4])[0]
            index += 4

            # Read the peak frequencies for the port
            peak_frequencies = []
            for _ in range(number_of_frequency_peaks):
                peak_frequency = struct.unpack(
                    '>d', response[index:index + 8])[0]
                peak_frequencies.append(peak_frequency)
                index += 8

            peak_frequencies_ports[tag_name] = {
                "number_of_peaks": number_of_frequency_peaks,
                "peak_frequencies": peak_frequencies,
            }
        calibration_data = {}

        # Tag 7, 3, 4, 5, 6 are used for
        # calibration and error correction (?)

        # Tag 7: Frequency errors
        while index < len(response):
            tag = response[index]
            if tag == 3:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(tag, f"unknown_tag_{tag}")
            number_of_frequency_errors = struct.unpack(
                '>I', response[index:index + 4])[0]
            index += 4

            frequency_errors = []
            for _ in range(number_of_frequency_errors):
                frequency_error = struct.unpack(
                    '>d', response[index:index + 8])[0]
                frequency_errors.append(frequency_error)
                index += 8

        # Tag 3-6
        #
        # linear fit equation and other data
        # for calibration and error-correcting

        # Tag 3 & 4 (linear fits)
        while index < len(response):
            tag = response[index]
            if tag == 5:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(tag, f"unknown_tag_{tag}")
            calibration_data[tag_name] = None
            calibration_data[tag_name] = {
                'slope': struct.unpack(
                    '>d', response[index:index + 8])[0],
                'intercept': struct.unpack(
                    '>d', response[index + 8:index + 16])[0],
                'r_value': struct.unpack(
                    '>d', response[index + 16:index + 24])[0]
            }
            index += 24

        # Tag 5 (number of reference lines & zero-crossings)
        tag = response[index]
        index += 1
        tag_name = TAG_PARSER.get('WSNS', {}).get(
            'NEXT', {}).get(tag, f"unknown_tag_{tag}")
        calibration_data[tag_name] = {
            'reference_lines': struct.unpack(
                '>I', response[index:index + 4])[0],
            'zero_crossings': struct.unpack(
                '>I', response[index + 4: index + 8])[0]
        }
        index += 8

        # tag 6 first and last crossing

        tag = response[index]
        index += 1
        tag_name = TAG_PARSER.get('WSNS', {}).get(
            'NEXT', {}).get(tag, f"unknown_tag_{tag}")
        calibration_data[tag_name] = {
            'first': struct.unpack(
                '>d', response[index:index + 8])[0],
            'last': struct.unpack(
                '>d', response[index + 8:index + 16])[0]
        }
        index += 16

        return {
            "peak_frequencies_ports": peak_frequencies_ports,
            "peak_widths_ports": peak_widths_ports,
            "peak_amplitudes_ports": peak_amplitudes_ports,
            "calibration_data": calibration_data,
        }

    # There are bugs in the code and mistakes
    # in the documentation for WSNS PARA.
    # Update this parser function after issues are solved.
    def _parse_wsns_para(self, response):
        wistsense_parameters = {}
        # Tag 1 (UINT32)
        index = 16
        while index < len(response):
            tag = response[index]
            if tag == 2:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1
        # Tags 2-6 (FLOAT64 values)
        while index < len(response):
            tag = response[index]
            if tag == 7:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack(
                '>d', response[index:index + 8])[0]
            index += 8

        # Tags 7-8 (UINT32)
        while index < len(response):
            tag = response[index]
            if tag == 101:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack(
                '>I', response[index:index + 4])[0]
            index += 4

        # Tag 101-150 (sensor port thresholds, FLOAT64)
        while index < len(response):
            tag = response[index]
            if tag == 9:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack(
                '>d', response[index:index + 8])[0]
            index += 8

        return wistsense_parameters

    def _parse_wsns_filt(self, response):
        """
        Parses the WSNS FILT response.
        :param response: The raw response from the WSNS FILT command.
        :return: A dictionary containing the output.
        """
        wsns_filt = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'FILT', {}).get(tag, f"unknown_tag_{tag}")
            wsns_filt[tag_name] = 0
            raise NotImplementedError("WSNS FILT not implemented yet.")

        return wsns_filt

    def _parse_wsns_rawb(self, response):
        """
        Parses the WSNS RAWB response.
        :param response: The raw response from the WSNS RAWB command.
        :return: A dictionary containing the parsed raw data.
        """
        wsns_rawb = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'RAWB', {}).get(tag, f"unknown_tag_{tag}")
            wsns_rawb[tag_name] = 0
            raise NotImplementedError("WSNS RAWB not implemented yet.")

        return wsns_rawb


if __name__ == "__main__":

    print(f"Connecting to {HOST}:{PORT}")
    with WistomClient(HOST, PORT, USER_ID, PASSWORD, use_ssh=True) as client:

        login_response = client.login()
        print("Login Response:", login_response)
        client.custom_api_request(COMMAND_ID['GET'], b'WSNS', b'NEXT', b'')

        profiler = cProfile.Profile()
        profiler.enable()
        client.get_smgr_info()
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        stats.print_stats(10)
