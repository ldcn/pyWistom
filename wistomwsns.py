"""
WistSense (WSNS) API operations for fiber optic sensing.

This module provides high-level methods for interacting with WistSense
fiber Bragg grating (FBG) interrogator functionality. WistSense provides
high-resolution peak detection for FBG sensors with self-calibration.

All operations require a connected and authenticated WistomClient instance.

See the WistSense User Guide (114605) for complete API details.

Example::

    >>> from pyWistom import WistomClient
    >>> from wistomwsns import WistSenseAPI
    >>> from wistomconfig import HOST, PORT, USER_ID, PASSWORD
    >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
    ...     wsns = WistSenseAPI(client)
    ...     peaks = wsns.get_next()
    ...     print(peaks['peak_frequencies_ports'])
"""

import struct
from wistomconstants import COMMAND_ID, SPECTRUM_TYPE, PORT_TYPE
from wistomtags import TAG_PARSER


class WistSenseAPI:
    """
    High-level API for WistSense fiber optic sensing operations.

    Provides methods to retrieve peak frequency data, configure parameters,
    and access debugging spectrum data from WistSense-enabled devices.

    :param client: Connected and authenticated WistomClient instance
    :type client: WistomClient

    Example::

        >>> from pyWistom import WistomClient
        >>> from wistomwsns import WistSenseAPI
        >>> with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
        ...     wsns = WistSenseAPI(client)
        ...     if wsns.get_enabled():
        ...         peaks = wsns.get_next()
    """

    def __init__(self, client):
        """
        Initialize WistSenseAPI with a WistomClient.

        :param client: Connected WistomClient instance
        :type client: WistomClient
        """
        self._client = client

    # -------------------------------------------------------------------------
    # Public GET Methods
    # -------------------------------------------------------------------------

    def get_enabled(self):
        """
        Check if WistSense is enabled on the device.

        :returns: True if WistSense is enabled, False otherwise
        :rtype: bool

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> if wsns.get_enabled():
            ...     print("WistSense is active")
            WistSense is active
        """
        response = self._client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'ENAB', b'')
        return self._parse_enab_response(response)

    def get_next(self):
        """
        Get current peak frequencies for all sensor ports.

        Returns peak frequency, width (FWHM), and amplitude data for each
        configured sensor port, along with calibration fit parameters.

        :returns: Dictionary containing:

            - ``peak_frequencies_ports`` (dict): Peak frequencies per port
            - ``peak_widths_ports`` (dict): FWHM values per port
            - ``peak_amplitudes_ports`` (dict): Peak amplitudes per port
            - ``calibration_data`` (dict): Linear fit and crossing data

        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> data = wsns.get_next()
            >>> for port, info in data['peak_frequencies_ports'].items():
            ...     print(f"{port}: {info['peak_frequencies']}")
            port_1_peak_frequencies: [191.234, 191.567, ...]
        """
        response = self._client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'NEXT', b'')
        return self._parse_next_response(response)

    def get_para(self):
        """
        Get WistSense parameters and calibration settings.

        Returns configuration parameters including HCN reference settings,
        filter constants, and per-port peak thresholds.

        :returns: Dictionary containing WistSense parameters:

            - ``lut_enabled`` (int): Use LUT for HCN check
            - ``peak_height_reference_lines`` (float): HCN peak height
            - ``frequency_delta`` (float): HCN frequency delta
            - ``filter_constant`` (float): Software filter constant
            - ``white_light_minimum`` (float): White light min threshold
            - ``interferometer_start_amplitude`` (float): Interferometer start
            - ``interferometer_minimum_step`` (int): Min step size
            - ``reference_averages`` (int): Number of reference averages
            - ``port_N_threshold`` (float): Per-port peak thresholds

        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> params = wsns.get_para()
            >>> print(f"Filter constant: {params['filter_constant']}")
            Filter constant: 0.1
        """
        response = self._client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'PARA', b'')
        return self._parse_para_response(response)

    def get_port(self):
        """
        Get port configuration (calibration vs sensor ports).

        Returns the type configuration for each port, indicating whether
        it is configured as a calibration port or sensor port.

        :returns: Dictionary mapping port names to port types
            (e.g., "Sensor", "Calibration", "Unknown")
        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> ports = wsns.get_port()
            >>> for port, ptype in ports.items():
            ...     print(f"{port}: {ptype}")
            port_1: Sensor
            port_2: Calibration
        """
        response = self._client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'PORT', b'')
        return self._parse_port_response(response)

    def get_data(self, spectrum_type=1, port=1, normalize=False):
        """
        Get spectrum data for debugging and analysis.

        Retrieves raw or processed spectrum data from the device for
        diagnostic purposes. Different spectrum types provide different
        views of the optical signal.

        :param spectrum_type: Type of spectrum to retrieve:

            - 1: Sensor spectrum (default)
            - 2: HCN reference spectrum
            - 3: Interferometer spectrum
            - 4: Sum spectrum
            - 5: Frequency scale

        :type spectrum_type: int
        :param port: Sensor port number (1-16)
        :type port: int
        :param normalize: Whether to normalize the spectrum
        :type normalize: bool

        :returns: Dictionary containing:

            - ``spectrum_type`` (str): Human-readable spectrum type
            - ``spectrum_data_length`` (int): Number of data points
            - ``spectrum_data_values`` (list): Spectrum amplitude values

        :rtype: dict

        :raises ValueError: If spectrum_type not in range 1-5
        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> spectrum = wsns.get_data(spectrum_type=1, port=1)
            >>> print(f"Points: {spectrum['spectrum_data_length']}")
            Points: 16384
        """
        if spectrum_type not in {1, 2, 3, 4, 5}:
            raise ValueError(f"spectrum_type must be 1-5, got {spectrum_type}")

        # Build request data: tag 1 (port), tag 2 (normalize), tag 10 (type)
        request_data = struct.pack('>BfBfBB',
                                   1, float(port),
                                   2, float(normalize),
                                   10, spectrum_type)
        response = self._client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'DATA', request_data)
        return self._parse_data_response(response, spectrum_type)

    def get_filt(self):
        """
        Get software filter settings for spectrum processing.

        :returns: Dictionary containing filter parameters:

            - ``filter_type`` (int): Type of filter applied
            - ``filter_coefficient`` (float): Filter coefficient value

        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> filt = wsns.get_filt()
            >>> print(f"Filter type: {filt.get('filter_type', 'N/A')}")
        """
        response = self._client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'FILT', b'')
        return self._parse_filt_response(response)

    def get_rawb(self, port=1):
        """
        Get raw spectrum without bias correction.

        Returns the raw optical spectrum before bias subtraction,
        useful for debugging and calibration verification.

        :param port: Sensor port number (1-16)
        :type port: int

        :returns: Dictionary containing:

            - ``port_selection`` (int): Selected port number
            - ``raw_spectrum`` (list): Raw spectrum values (FLOAT32)

        :rtype: dict

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> raw = wsns.get_rawb(port=1)
            >>> print(f"Raw samples: {len(raw.get('raw_spectrum', []))}")
        """
        request_data = struct.pack('>BB', 1, port)
        response = self._client.custom_api_request(
            COMMAND_ID['GET'], b'WSNS', b'RAWB', request_data)
        return self._parse_rawb_response(response)

    # -------------------------------------------------------------------------
    # Public SET Methods
    # -------------------------------------------------------------------------

    def set_enabled(self, enabled):
        """
        Enable or disable WistSense.

        :param enabled: True to enable, False to disable
        :type enabled: bool

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> wsns.set_enabled(True)
        """
        request_data = struct.pack('>BB', 1, int(bool(enabled)))
        self._client.custom_api_request(
            COMMAND_ID['SET'], b'WSNS', b'ENAB', request_data)

    def set_para(self, **kwargs):
        """
        Set WistSense parameters.

        Accepts keyword arguments matching parameter names from get_para().
        Only specified parameters are modified; others retain current values.

        :param lut_enabled: Use LUT for HCN check (0 or 1)
        :type lut_enabled: int, optional
        :param peak_height_reference_lines: HCN peak height threshold
        :type peak_height_reference_lines: float, optional
        :param frequency_delta: HCN frequency delta
        :type frequency_delta: float, optional
        :param filter_constant: Software filter constant
        :type filter_constant: float, optional
        :param white_light_minimum: White light minimum threshold
        :type white_light_minimum: float, optional
        :param interferometer_start_amplitude: Interferometer start amplitude
        :type interferometer_start_amplitude: float, optional
        :param interferometer_minimum_step: Interferometer minimum step
        :type interferometer_minimum_step: int, optional
        :param reference_averages: Number of reference averages
        :type reference_averages: int, optional

        :raises ValueError: If unknown parameter name provided
        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> wsns.set_para(filter_constant=0.15, reference_averages=10)
        """
        request_data = self._build_para_request(kwargs)
        self._client.custom_api_request(
            COMMAND_ID['SET'], b'WSNS', b'PARA', request_data)

    def set_filt(self, filter_type=None, filter_coefficient=None):
        """
        Set software filter parameters.

        :param filter_type: Type of filter to apply
        :type filter_type: int, optional
        :param filter_coefficient: Filter coefficient value
        :type filter_coefficient: float, optional

        :raises TimeoutError: If device does not respond within timeout
        :raises ConnectionError: If not connected to device

        Example::

            >>> wsns = WistSenseAPI(client)
            >>> wsns.set_filt(filter_type=1, filter_coefficient=0.5)
        """
        request_data = b''
        if filter_type is not None:
            request_data += struct.pack('>BB', 1, filter_type)
        if filter_coefficient is not None:
            request_data += struct.pack('>Bd', 2, filter_coefficient)
        if request_data:
            self._client.custom_api_request(
                COMMAND_ID['SET'], b'WSNS', b'FILT', request_data)

    # -------------------------------------------------------------------------
    # Response Parsers
    # -------------------------------------------------------------------------

    def _parse_enab_response(self, response):
        """
        Parse WSNS ENAB response.

        :param response: Raw binary response from device
        :type response: bytes
        :returns: True if enabled, False otherwise
        :rtype: bool
        """
        index = 16  # Skip header
        if index < len(response):
            tag = response[index]
            index += 1
            if tag == 1:
                return bool(response[index])
        return False

    def _parse_next_response(self, response):
        """
        Parse WSNS NEXT response with peak frequency data.

        :param response: Raw binary response from device
        :type response: bytes
        :returns: Dictionary with peak frequencies, widths, amplitudes,
            and calibration data
        :rtype: dict
        """
        peak_frequencies_ports = {}
        peak_widths_ports = {}
        peak_amplitudes_ports = {}
        index = 16  # Start after header

        # Tags 101-116: Peak frequencies per port
        # Tags 151-166: FWHM (width) per port
        # Tags 201-216 or 221-236: Amplitudes per port

        while index < len(response):
            port_tag = response[index]
            # Tag 7 starts calibration/error data section
            if port_tag == 7:
                break
            index += 1

            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(port_tag, f"unknown_tag_{port_tag}")

            # Handle peak widths (151-166)
            if 151 <= port_tag <= 166:
                number_of_peaks = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
                peak_widths = []
                for _ in range(number_of_peaks):
                    peak_width = struct.unpack(
                        '>d', response[index:index + 8])[0]
                    peak_widths.append(peak_width)
                    index += 8
                peak_widths_ports[tag_name] = {
                    "number_of_peaks": number_of_peaks,
                    "peak_widths": peak_widths,
                }
                continue

            # Handle peak amplitudes (201-216 or 221-236)
            if 201 <= port_tag <= 236:
                number_of_peaks = struct.unpack(
                    '>I', response[index:index + 4])[0]
                index += 4
                peak_amplitudes = []
                for _ in range(number_of_peaks):
                    peak_amplitude = struct.unpack(
                        '>d', response[index:index + 8])[0]
                    peak_amplitudes.append(peak_amplitude)
                    index += 8
                peak_amplitudes_ports[tag_name] = {
                    "number_of_peaks": number_of_peaks,
                    "peak_amplitudes": peak_amplitudes,
                }
                continue

            # Handle peak frequencies (101-116)
            number_of_peaks = struct.unpack(
                '>I', response[index:index + 4])[0]
            index += 4

            peak_frequencies = []
            for _ in range(number_of_peaks):
                peak_frequency = struct.unpack(
                    '>d', response[index:index + 8])[0]
                peak_frequencies.append(peak_frequency)
                index += 8

            peak_frequencies_ports[tag_name] = {
                "number_of_peaks": number_of_peaks,
                "peak_frequencies": peak_frequencies,
            }

        calibration_data = {}

        # Tag 7: Frequency errors
        while index < len(response):
            tag = response[index]
            if tag == 3:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(tag, f"unknown_tag_{tag}")
            number_of_errors = struct.unpack(
                '>I', response[index:index + 4])[0]
            index += 4

            frequency_errors = []
            for _ in range(number_of_errors):
                error = struct.unpack('>d', response[index:index + 8])[0]
                frequency_errors.append(error)
                index += 8
            calibration_data[tag_name] = frequency_errors

        # Tags 3-4: Linear fits
        while index < len(response):
            tag = response[index]
            if tag == 5:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(tag, f"unknown_tag_{tag}")
            calibration_data[tag_name] = {
                'slope': struct.unpack('>d', response[index:index + 8])[0],
                'intercept': struct.unpack(
                    '>d', response[index + 8:index + 16])[0],
                'r_value': struct.unpack(
                    '>d', response[index + 16:index + 24])[0]
            }
            index += 24

        # Tag 5: Number of data points
        if index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(tag, f"unknown_tag_{tag}")
            calibration_data[tag_name] = {
                'reference_lines': struct.unpack(
                    '>I', response[index:index + 4])[0],
                'zero_crossings': struct.unpack(
                    '>I', response[index + 4:index + 8])[0]
            }
            index += 8

        # Tag 6: First and last crossing
        if index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'NEXT', {}).get(tag, f"unknown_tag_{tag}")
            calibration_data[tag_name] = {
                'first': struct.unpack('>d', response[index:index + 8])[0],
                'last': struct.unpack('>d', response[index + 8:index + 16])[0]
            }
            index += 16

        return {
            "peak_frequencies_ports": peak_frequencies_ports,
            "peak_widths_ports": peak_widths_ports,
            "peak_amplitudes_ports": peak_amplitudes_ports,
            "calibration_data": calibration_data,
        }

    def _parse_para_response(self, response):
        """
        Parse WSNS PARA response with WistSense parameters.

        :param response: Raw binary response from device
        :type response: bytes
        :returns: Dictionary of WistSense parameters
        :rtype: dict
        """
        params = {}
        index = 16

        # Tag 1: UINT8 (lut_enabled)
        while index < len(response):
            tag = response[index]
            if tag == 2:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            params[tag_name] = struct.unpack(
                '>B', response[index:index + 1])[0]
            index += 1

        # Tags 2-6: FLOAT64 values
        while index < len(response):
            tag = response[index]
            if tag == 7:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            params[tag_name] = struct.unpack(
                '>d', response[index:index + 8])[0]
            index += 8

        # Tags 7-8: UINT32
        while index < len(response):
            tag = response[index]
            if tag >= 101:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            params[tag_name] = struct.unpack(
                '>I', response[index:index + 4])[0]
            index += 4

        # Tags 101-150: Port thresholds (FLOAT64)
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PARA', {}).get(tag, f"unknown_tag_{tag}")
            params[tag_name] = struct.unpack(
                '>d', response[index:index + 8])[0]
            index += 8

        return params

    def _parse_port_response(self, response):
        """
        Parse WSNS PORT response with port configuration.

        :param response: Raw binary response from device
        :type response: bytes
        :returns: Dictionary mapping port names to types
        :rtype: dict
        """
        sensor_ports = {}
        index = 16

        while index < len(response):
            port_tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'PORT', {}).get(port_tag, f'unknown_port_{port_tag}')
            type_name = PORT_TYPE.get(response[index], "Unknown")
            sensor_ports[tag_name] = type_name
            index += 1

        return sensor_ports

    def _parse_data_response(self, response, spectrum_type):
        """
        Parse WSNS DATA response with spectrum data.

        :param response: Raw binary response from device
        :type response: bytes
        :param spectrum_type: Requested spectrum type (1-5)
        :type spectrum_type: int
        :returns: Dictionary with spectrum data
        :rtype: dict
        """
        spectrum_data = {}
        index = 16

        if spectrum_type in {1, 2, 3, 4, 5}:
            if index < len(response):
                tag = response[index]
                index += 1

                type_name = SPECTRUM_TYPE.get(spectrum_type, "Unknown")
                tag_name = TAG_PARSER.get('WSNS', {}).get(
                    'DATA', {}).get(tag, f"unknown_tag_{tag}")

                data_length = struct.unpack('>I', response[index:index + 4])[0]
                index += 4

                spectrum_values = []
                for _ in range(data_length):
                    value = struct.unpack('>f', response[index:index + 4])[0]
                    spectrum_values.append(value)
                    index += 4

                spectrum_data = {
                    "spectrum_type": type_name,
                    "spectrum_data_length": data_length,
                    "spectrum_data_values": spectrum_values,
                }

        return spectrum_data

    def _parse_filt_response(self, response):
        """
        Parse WSNS FILT response with filter settings.

        :param response: Raw binary response from device
        :type response: bytes
        :returns: Dictionary with filter parameters
        :rtype: dict
        """
        filt_data = {}
        index = 16

        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'FILT', {}).get(tag, f"unknown_tag_{tag}")

            if tag == 1:  # filter_type (UINT8)
                filt_data[tag_name] = response[index]
                index += 1
            elif tag == 2:  # filter_coefficient (FLOAT64)
                filt_data[tag_name] = struct.unpack(
                    '>d', response[index:index + 8])[0]
                index += 8

        return filt_data

    def _parse_rawb_response(self, response):
        """
        Parse WSNS RAWB response with raw spectrum data.

        :param response: Raw binary response from device
        :type response: bytes
        :returns: Dictionary with raw spectrum data
        :rtype: dict
        """
        rawb_data = {}
        index = 16

        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get(
                'RAWB', {}).get(tag, f"unknown_tag_{tag}")

            if tag == 1:  # port_selection (UINT8)
                rawb_data[tag_name] = response[index]
                index += 1
            elif tag == 11:  # raw_spectrum (length + FLOAT32[])
                data_length = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                spectrum = []
                for _ in range(data_length):
                    value = struct.unpack('>f', response[index:index + 4])[0]
                    spectrum.append(value)
                    index += 4
                rawb_data[tag_name] = spectrum

        return rawb_data

    # -------------------------------------------------------------------------
    # Request Builders
    # -------------------------------------------------------------------------

    def _build_para_request(self, params):
        """
        Build WSNS PARA SET request data.

        :param params: Dictionary of parameters to set
        :type params: dict
        :returns: Packed binary request data
        :rtype: bytes
        """
        # Parameter name to (tag, format) mapping
        param_map = {
            'lut_enabled': (1, '>BB'),
            'peak_height_reference_lines': (2, '>Bd'),
            'frequency_delta': (3, '>Bd'),
            'filter_constant': (4, '>Bd'),
            'white_light_minimum': (5, '>Bd'),
            'interferometer_start_amplitude': (6, '>Bd'),
            'interferometer_minimum_step': (7, '>BI'),
            'reference_averages': (8, '>BI'),
        }

        # Add port thresholds (port_1_threshold through port_50_threshold)
        for i in range(50):
            param_map[f'port_{i + 1}_threshold'] = (101 + i, '>Bd')

        request_data = b''
        for name, value in params.items():
            if name not in param_map:
                raise ValueError(f"Unknown parameter: {name}")
            tag, fmt = param_map[name]
            request_data += struct.pack(fmt, tag, value)

        return request_data
