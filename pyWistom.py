"""
pyWistom - Python client for Wistom fiber optic sensing devices.

This module provides the :class:`WistomClient` class for communicating with
Proximion fiber optic sensing devices using the Wistom binary API protocol.

The client supports both direct TCP connections and SSH tunneling for
remote access. All API commands use big-endian binary encoding with
4-byte ASCII identifiers for applications and operations.

See the API specification (100051) for complete protocol details.

Example::

    >>> from pyWistom import WistomClient
    >>> from wistomconfig import HOST, PORT, USER_ID, PASSWORD
    >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
    ...     info = client.get_smgr_info()
    ...     temps = client.get_smgr_temp()
"""
import socket
import struct
import cProfile
import pstats

from wistomconfig import (
    HOST,
    PORT,
    USER_ID,
    PASSWORD,
    API_VERSION
)

from wistomconstants import (
    COMMAND_ID,
    LOGIN_RESULT,
    ERROR_CODE,
    SPECTRUM_TYPE,
    PORT_TYPE,
)

from wistomresponses import (
    RESPONSE_HEADER_PARSER,
    RESPONSE_PARSER,
)

from wistomtags import (
    TAG_PARSER,
)

from wistomconnection import WistomConnection


MAX_TAGS = 255


class WistomClient:
    """
    Client for communicating with Wistom fiber optic sensing devices.

    Provides methods to interact with the Wistom API over TCP sockets,
    with optional SSH tunneling for remote connections.

    :param host: IP address or hostname of the Wistom device
    :param port: TCP port number (default: 7734)
    :param user_id: Username for authentication
    :param password: Password for authentication
    :param use_ssh: Enable SSH tunneling for remote connections

    Example::

        >>> from pyWistom import WistomClient
        >>> from wistomconfig import HOST, PORT, USER_ID, PASSWORD
        >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
        ...     info = client.get_smgr_info()
        ...     print(info['response']['software_revision'])
        R2.1.0
    """

    def __init__(self, host, port, user_id, password, use_ssh=False):
        """
        Initialize a WistomClient instance.

        :param host: IP address or hostname of the Wistom device
        :type host: str
        :param port: TCP port number for API connection
        :type port: int
        :param user_id: Username for authentication
        :type user_id: str
        :param password: Password for authentication
        :type password: str
        :param use_ssh: Enable SSH tunneling for remote connections
        :type use_ssh: bool
        """
        self.connection = WistomConnection(
            host, port, use_ssh, user_id, password)

        self.user_id = user_id
        self.password = password

    def __enter__(self):
        """Enter context manager, connect and login to device."""
        self.connection.connect()
        self.login()
        return self

    def __exit__(self, type, value, traceback):
        """Exit context manager and disconnect from device."""
        self.connection.disconnect()

    def login(self):
        """
        Authenticate with the Wistom device.

        Starts an API session using the configured user credentials.
        Called automatically when using the context manager.
        See API spec LGIN (100051).

        :returns: Raw login response bytes containing user level or error code
        :rtype: bytes

        :raises ConnectionError: If not connected to device

        Example::

            >>> client = WistomClient(HOST, PORT, USER_ID, PASSWORD)
            >>> client.connection.connect()
            >>> response = client.login()
            >>> # User level 2 = customer access
        """
        response = self.connection.login(
            self.user_id,
            self.password,
            COMMAND_ID['LOGIN'],
            b'LGIN',
            API_VERSION.encode('ascii')
        )
        return response

    def __increment_token(self):
        """Increment and return the request token for message sequencing."""
        return self.connection.increment_token()

    def __get_token(self):
        """Get the current request token value."""
        return self.connection.get_token()

    # API Commands

    def get_smgr_info(self):
        """
        Get product information from the System Manager.

        Retrieves hardware, software, sensor, and calibration information.
        See API spec SMGR INFO (100051).

        :returns: Dictionary with product information:
            - ``hardware_product_number`` (str): Hardware article number
            - ``hardware_id_number`` (str): Unique ID from temp sensor on WEB
            - ``hardware_revision`` (str): WEB board revision
            - ``hardware_serial_number`` (str): Hardware serial number
            - ``sensor_product_number`` (str): Sensor article number
            - ``sensor_serial_number`` (str): Sensor serial number
            - ``software_product_number`` (str): Software product number
            - ``software_revision`` (str): Software revision
            - ``firmware_revision`` (str): FPGA firmware revision
            - ``pld_revision`` (str): WEB2017 driver version
            - ``bootstrap_revision`` (str): Linux version
            - ``unit_serial`` (str): Complete unit serial number
            - ``production_date`` (str): Production date
            - ``start_calibration_frequency`` (float): Start freq of calibration (Hz)
            - ``end_calibration_frequency`` (float): Stop freq of calibration (Hz)
            - ``start_calibration_temperature`` (float): Start temp of calibration (°C)
            - ``end_calibration_temperature`` (float): Stop temp of calibration (°C)
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     info = client.get_smgr_info()
            ...     print(f"SW: {info['response']['software_revision']}")
            ...     print(f"Unit: {info['response']['unit_serial']}")
            SW: R2.1.0
            Unit: WS-1234567
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'INFO',
            b''
        )

    def get_smgr_network_info(self):
        """
        Get network configuration from the System Manager.

        Retrieves IP settings including address, subnet, gateway, and hostname.
        See API spec SMGR IP## (100051).

        :returns: Dictionary with network configuration:
            - ``ip_address`` (str): Device IP address
            - ``subnet_mask`` (str): Subnet mask
            - ``gateway_address`` (str): Default gateway
            - ``host_name`` (str): Device hostname
            - ``mac_address`` (str): MAC address
            - ``listening_port`` (int): TCP port for API connections
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     net = client.get_smgr_network_info()
            ...     print(f"IP: {net['response']['ip_address']}")
            ...     print(f"Port: {net['response']['listening_port']}")
            IP: 10.44.40.218
            Port: 7734
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'IP##',
            b''
        )

    def get_smgr_serial_settings(self):
        """
        Get serial port (RS232) settings from the System Manager.

        Retrieves configuration for serial interface 1.
        See API spec SMGR SER# (100051).

        :returns: Dictionary with serial port settings:
            - ``serial_interface`` (int): Interface number (always 1)
            - ``baud_rate`` (int): Baud rate (e.g., 9600, 115200)
            - ``data_bits`` (int): Data bits (5-8)
            - ``stop_bits`` (int): Stop bits (1-2)
            - ``parity_bit`` (int): Parity (0=none, 1=odd, 2=even)
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     serial = client.get_smgr_serial_settings()
            ...     print(f"Baud: {serial['response']['baud_rate']}")
            Baud: 115200
        """
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
        """
        Get current date and time from the System Manager.

        Retrieves the device's real-time clock values.
        See API spec SMGR TIME (100051).

        :returns: Dictionary with date/time components:
            - ``year`` (int): Year (e.g., 2025)
            - ``month`` (int): Month (1-12)
            - ``day`` (int): Day of month (1-31)
            - ``hour`` (int): Hour (0-23)
            - ``minute`` (int): Minute (0-59)
            - ``second`` (int): Second (0-59)
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     time = client.get_smgr_time()
            ...     r = time['response']
            ...     print(f"{r['year']}-{r['month']:02d}-{r['day']:02d}")
            2025-12-13
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'TIME',
            b''
        )

    def get_smgr_temp(self):
        """
        Get temperature readings from the System Manager.

        Retrieves board, sensor, and FPGA temperatures.
        See API spec SMGR TEMP (100051).

        :returns: Dictionary with temperature data:

            - ``board_temperature`` (float): Electronic board temperature in °C
            - ``sensor_temperature`` (float): Sensor temperature in °C
            - ``sensor_temperature_derivative`` (float): Temperature rate of
              change in °C/s, averaged over ~200 measurements
            - ``configured_min_temperature`` (float): User-configured min temp
              limit for alarms in °C
            - ``configured_max_temperature`` (float): User-configured max temp
              limit for alarms in °C
            - ``fpga_temperature`` (float): FPGA internal temperature in °C

        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     temps = client.get_smgr_temp()
            ...     print(f"Board: {temps['response']['board_temperature']:.1f}°C")
            ...     print(f"FPGA: {temps['response']['fpga_temperature']:.1f}°C")
            Board: 27.3°C
            FPGA: 45.2°C
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'TEMP',
            b''
        )

    def get_smgr_uptime(self):
        """
        Get system uptime from the System Manager.

        Retrieves time since boot/restart and system load.
        See API spec SMGR UPTI (100051).

        :returns: Dictionary with uptime data:

            - ``uptime`` (float): Time since OS started (power on or hard
              restart via SMGR REST 1 0) in seconds
            - ``app_uptime`` (float): Time since application started (soft
              restart via SMGR REST 1 1) in seconds
            - ``system_load_average`` (float): Linux load average over 1 minute.
              Value below 1.0 means system is below maximum load.

        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     uptime = client.get_smgr_uptime()
            ...     hours = uptime['response']['uptime'] / 3600
            ...     print(f"Uptime: {hours:.1f} hours")
            Uptime: 124.5 hours
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'UPTI',
            b''
        )

    def get_snmp_agent_listening_port(self):
        """
        Get SNMP agent configuration from the System Manager.

        Retrieves the UDP port where the SNMP agent listens.
        See API spec SMGR SCFG (100051).

        :returns: Dictionary with SNMP configuration:
            - ``agent_port`` (int): UDP port for SNMP agent (default: 161)
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     snmp = client.get_snmp_agent_listening_port()
            ...     print(f"SNMP port: {snmp['response']['agent_port']}")
            SNMP port: 161
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'SCFG',
            b''
        )

    def get_snmp_trap_receivers(self):
        """
        Get list of SNMP trap receivers from the System Manager.

        Retrieves IP addresses and ports of configured trap managers.
        See API spec SMGR SLTR (100051).

        :returns: Dictionary with trap receiver list. Each receiver has:
            - ``trap_ip_address`` (str): IP address of trap manager
            - ``trap_port`` (int): UDP port for traps
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     traps = client.get_snmp_trap_receivers()
            ...     print(traps['response'])
            {'trap_ip_address': '10.44.40.1', 'trap_port': 162}
        """
        self.__increment_token()
        return self.__send_request(
            COMMAND_ID['GET'],
            b'SMGR',
            b'SLTR',
            b''
        )

    def custom_api_request(self, command_id, app_id, op_id, data):
        """
        Send a custom API request to the Wistom device.

        Allows sending any valid Wistom API command with custom parameters.
        Use this for commands not yet wrapped by dedicated methods.

        :param command_id: Command type from ``COMMAND_ID`` dict
            (e.g., ``COMMAND_ID['GET']``, ``COMMAND_ID['SET']``)
        :type command_id: bytes
        :param app_id: 4-byte ASCII application identifier
            (e.g., ``b'SMGR'``, ``b'WSNS'``, ``b'OPM#'``)
        :type app_id: bytes
        :param op_id: 4-byte ASCII operation identifier
            (e.g., ``b'INFO'``, ``b'TEMP'``, ``b'DATA'``)
        :type op_id: bytes
        :param data: Tag data bytes for the request (can be empty ``b''``)
        :type data: bytes

        :returns: Parsed response dictionary with 'header' and 'response' keys
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device

        Example::

            >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
            ...     # Get sensor spectrum (WSNS DATA with tag 0x0a = spectrum type)
            ...     spectrum = client.custom_api_request(
            ...         COMMAND_ID['GET'],
            ...         b'WSNS',
            ...         b'DATA',
            ...         bytes.fromhex("0a01")  # Tag 10, value 1 (sensor spectrum)
            ...     )
            ...     print(f"Points: {len(spectrum['response']['spectrum_data_values'])}")
            Points: 16384
        """
        self.__increment_token()
        return self.__send_request(
            command_id,
            app_id,
            op_id,
            data
        )

    def custom_api_request_raw(self, command_id, app_id, op_id, data):
        """
        Send a custom API request and return raw response.

        Same as :meth:`custom_api_request` but returns the raw parsed response.
        Useful for debugging or when custom parsing is needed.

        :param command_id: Command type from ``COMMAND_ID`` dict
        :type command_id: bytes
        :param app_id: 4-byte ASCII application identifier
        :type app_id: bytes
        :param op_id: 4-byte ASCII operation identifier
        :type op_id: bytes
        :param data: Tag data bytes for the request
        :type data: bytes

        :returns: Parsed response dictionary
        :rtype: dict

        :raises TimeoutError: If device does not respond within 5 seconds
        :raises ConnectionError: If not connected to device
        """
        self.__increment_token()
        return self.__send_request(
            command_id,
            app_id,
            op_id,
            data
        )

    ##################
    # Private methods

    # Helper methods
    def __send_request(self, cid, app_id, op_id, request_data):
        """
        Send a binary API request to the Wistom device.

        Constructs the binary payload according to the Wistom protocol
        and sends it over the TCP socket connection.

        :param cid: Command identifier (2 bytes)
        :param app_id: Application identifier (4 bytes ASCII)
        :param op_id: Operation identifier (4 bytes ASCII)
        :param request_data: Tag data for the request
        :returns: Parsed response dictionary
        :raises ConnectionError: If not connected
        :raises TimeoutError: If no response within 5 seconds
        """
        data_length = len(request_data)
        payload = (cid
                   + self.connection.token.to_bytes(2, 'big')
                   + app_id
                   + op_id
                   + data_length.to_bytes(4, 'big')
                   + request_data)
        if not self.connection.socket:
            raise ConnectionError("Not connected to server")

        # Set a timeout for the socket
        self.connection.socket.settimeout(5.0)

        try:
            self.connection.socket.sendall(payload)
            # Receive the full response in smaller chunks
            response = self.__receive_full_response()
        except socket.timeout:
            raise TimeoutError("Request timed out after 5 seconds")
        finally:
            # Reset the timeout to None (blocking mode) after the request
            self.connection.socket.settimeout(None)

        return self.__handle_response(app_id, op_id, response, request_data)

    def __receive_full_response(self):
        """
        Receive complete response from device.

        Reads the 16-byte header first to determine payload length,
        then receives remaining data in chunks until complete.

        :returns: Complete response bytes including header
        :raises ConnectionError: If header incomplete or connection closed
        """
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
        """
        Route response to appropriate parser based on command ID.

        Parses the response header and delegates to the correct
        response parser based on app_id and op_id.

        :param app_id: Application identifier from request
        :param op_id: Operation identifier from request
        :param response: Raw response bytes
        :param request_data: Original request data (for parsers that need it)
        :returns: Dictionary with 'header' and 'response' keys
        """
        cid = response[0:2]
        header_parser_name = RESPONSE_HEADER_PARSER.get(
            cid, "__parse_unknown_command")
        header_parser = getattr(self, header_parser_name,
                                self.__parse_unknown_command)
        parsed_header = header_parser(response)

        if cid == (COMMAND_ID["GETRES"] or COMMAND_ID["LOGINRES"]):
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
        else:
            return parsed_header

    def __parse_unknown_command(self, response):
        """Parse response with unrecognized command ID."""
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
        """Return raw bytes for unrecognized response types."""
        return {
            "bytes": response[16:],
            "hex": response[16:].hex(),
        }

    def _parse_loginres_header(self, response):
        """Parse LOGINRES (0x0101) response header."""
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')

        return {
            "Login result": f"{app_id} {op_id}",
            "Token": f"{token}",
        }

    def _parse_setack_header(self, response):
        """Parse SETACK (0x0103) response header."""
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')

        return {
            "SET Acknowledged": f"{app_id} {op_id}",
            "Token": f"{token}",
        }

    def _parse_setnack_header(self, response):
        """Parse SETNACK (0x0203) response header with error details."""
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
        """Parse GETERR (0x0204) response header with error details."""
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
        """Parse GETRES (0x0104) response header."""
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

    def _parse_apiv2_login_response(self, response):
        """Parse API v2 login response with user level."""
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
        """Parse LGIN UINF response with user name and level."""
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
        """Parse LGIN SINF response with active session info."""
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
        """Parse SMGR SER# response with RS232 settings."""
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
        """Parse SMGR IP## response with network configuration."""
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
        """Parse SMGR TIME response with date/time components."""
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
        """Parse SMGR INFO response with product/calibration data."""
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
        """Parse SMGR UPTI response with uptime and load data."""
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
        """Parse SMGR TEMP response with temperature readings."""
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
        """Parse SMGR SLTR response with trap receiver list."""
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
        """Parse SMGR SCFG response with SNMP agent configuration."""
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
        """Parse SMGR INST response with installed features."""
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
    # Pulse frequency control API function parsers
    # For reference, see Wistom API documentation (document 100051)
    ###################################################################

    def _parse_frequency_regulator_values(self, response):
        """Parse PULF REGV response with frequency regulator data."""
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
    # Wistsense API function parsers
    # For reference, see Wistom API documentation (document 100051)
    # For high-level WSNS operations, see wistomwsns.py (WistSenseAPI class)
    # ------------------------------------------------------------------

    def _parse_wistsense_enable(self, response):
        """
        Parse WSNS ENAB response.

        :param response: Raw binary response from device
        :type response: bytes
        :returns: Dictionary with enabled status
        :rtype: dict
        """
        index = 16  # Skip header
        result = {'enabled': False}
        if index < len(response):
            tag = response[index]
            index += 1
            if tag == 1:
                result['enabled'] = bool(response[index])
        return result

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
        """Parse WSNS PORT response with calibration/sensor port config."""
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
        """Parse WSNS NEXT response with peak frequency data."""
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
        """Parse WSNS PARA response with WistSense parameters."""
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
