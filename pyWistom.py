import socket
import struct

from wistomconfig import (
    HOST, 
    PORT, 
    USER_ID, 
    PASSWORD, 
    API_VERSION
)

from wistomconstants import (
    COMMAND_ID,
    ALARM_ID,
    LOGIN_RESULT,
    RESPONSE_HEADER_PARSER,
    RESPONSE_PARSER,
    ERROR_CODE,
    TAG_PARSER,
    PORT_TYPE,
)

from wistomconnection import WistomConnection

class WistomClient:
    def __init__(self, host, port, user_id, password):
        self.connection = WistomConnection(host, port)
        self.user_id = user_id
        self.password = password
        self.token = 0

    ## Context manager methods
    def __enter__(self):
        self.connection.connect()
        self.login()
        return self
    
    def __exit__(self, type, value, traceback):
        self.connection.disconnect()

    ## Login method
    ## Creates the login payload as described in Page 74 Table 11-2
    ## of the Wistom User Guide
    def login(self):
        cid = COMMAND_ID['LOGIN']
        app_id = b'LGIN'
        op_id = API_VERSION.encode('ascii')
        user_id_bytes = self.user_id.encode('ascii')
        password_bytes = self.password.encode('ascii')
        data = (user_id_bytes + b'\x00' 
                   + password_bytes + b'\x00')
        return self.__send_request(cid, app_id, op_id, data)
    
    # API Commands

    def get_smgr_info(self):
        self.__increment_token()
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'INFO', b'')

    def get_smgr_network_info(self):
        self.__increment_token()
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'IP##', b'')
    
    def get_smgr_serial_settings(self):
        self.__increment_token()
        # There is only one serial interface, 0x01, but supplying the (tag number and) interface number is required.
        # If not supplied, the request will result in a GETERR.
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'SER#', b'\x01\x01')
    
    def get_smgr_time(self):
        self.__increment_token()
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'TIME', b'')
    
    def get_smgr_temp(self):
        self.__increment_token()
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'TEMP', b'')
    
    def get_smgr_uptime(self):
        self.__increment_token()
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'UPTI', b'')
    
    def get_snmp_agent_listening_port(self):
        self.__increment_token()
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'SCFG', b'')
    
    def get_snmp_trap_receivers(self):
        self.__increment_token()
        return self.__send_request(COMMAND_ID['GET'], b'SMGR', b'SLTR', b'')
    
    def custom_api_request(self, command_id, app_id, op_id, data):
        self.__increment_token()
        return self.__send_request(command_id, app_id, op_id, data)
    
    def custom_api_request_raw(self, command_id, app_id, op_id, data):
        self.__increment_token()
        return self.__send_request(command_id, app_id, op_id, data)

    ##################
    ## Private methods

    ## Helper methods
    def __send_request(self, cid, app_id, op_id, request_data):
        data_length = len(request_data)
        payload = (cid 
                   + self.token.to_bytes(2, 'big')
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
        # Read the header first to determine the total payload size
        header = self.connection.socket.recv(16)
        if len(header) < 16:
            raise ConnectionError("Incomplete response header received")

        data_length = int.from_bytes(header[12:16], 'big')
        total_length = 16 + data_length

        # Receive the remaining payload in chunks
        response = header
        while len(response) < total_length:
            chunk = self.connection.socket.recv(min(4096, total_length - len(response)))
            if not chunk:
                raise ConnectionError("Connection closed before full payload was received")
            response += chunk

        return response
    
    def __handle_response(self, app_id, op_id, response, request_data=None):
        cid = response[0:2]
        header_parser_name = RESPONSE_HEADER_PARSER.get(cid, "__parse_unknown_command")
        header_parser = getattr(self, header_parser_name, self.__parse_unknown_command)
        parsed_header = header_parser(response)
        
        if cid == (COMMAND_ID["GETRES"] or COMMAND_ID["LOGINRES"]):
            parser_name = RESPONSE_PARSER.get(app_id.decode('ascii'), {}).get(op_id.decode('ascii'), "_parse_unknown_response")
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
            "Tag number": int.from_bytes(tag_number, 'big') if tag_number != b'\x00\x00' else None
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
            "Tag number": int.from_bytes(tag_number, 'big') if tag_number != b'\x00\x00' else None
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
          
    def __increment_token(self):
        self.token += 1
        return self.token
    
    ## Parses the login response into a human-readable format
    def _parse_apiv2_login_response(self, response):        
        command_id = response[0:2]
        login_result = response[-4:]
        command_name = next((key for key, value in COMMAND_ID.items() if value == command_id), "Unknown Command")
        login_result_name = next((key for key, value in LOGIN_RESULT.items() if value == login_result), "Unknown Login Result")

        return {
                "command_id": command_name,
                "login_result": login_result_name
                }
    
    ###################################################################
    ## Parsers for getRes responses                                  ##
    ## For reference, see Wistom API documentation (document 100051) ##
    ###################################################################

    def _parse_login_user_info_response(self, response, data=None):
        user_info = {}
        index = 16
        payload = response[index:]
        
        while index < len(payload):
            tag = payload[index]
            index += 1
            tag_name = TAG_PARSER.get('LGIN', {}).get('UINF', {}).get(tag, f"unknown_tag_{tag}")

            # Find the null byte and slice the string directly
            null_terminated_string_end = payload.find(b'\x00', index)
            if (null_terminated_string_end == -1):
                break
            user_name = payload[:null_terminated_string_end].decode('ascii')


            user_info[tag_name] = user_name
            index += (null_terminated_string_end - index + 1)
            tag = payload[index]
            tag_name = TAG_PARSER.get('LGIN', {}).get('UINF', {}).get(tag, f"unknown_tag_{tag}")
            user_level = struct.unpack('>I', payload[index:index + 4])[0]
            user_info[tag_name] = user_level
            print(user_info)

        return user_info
            

    def _parse_login_session_info_response(self, response, data=None):
        
        index = 0
        logged_in_users = 0
        data = response[16:]
        parsed_data = {}

        while index < len(data):
            # read the username tag
            if index + 1 > len(data):
                break
            tag_user = data[index]
            index += 1

            # Read the username
            null_terminated_string_end = data.find(b'\x00', index)
            if null_terminated_string_end == -1:
                break
            user_string = data[index:null_terminated_string_end].decode('ascii')
            index += (null_terminated_string_end - index + 1)

            # Read the process id tag
            if index + 1 > len(data):
                break
            tag_pid = data[index]
            index += 1

            # Read the process id
            if index + 4 > len(data):
                break
            pid = struct.unpack('>I', data[index:index + 4])[0]
            index += 4

            # parse the data
            logged_in_users += 1
            parsed_data[f"user_{logged_in_users}"] = user_string
            parsed_data[f"process_id_{logged_in_users}"] = pid

        return {
            "logged_in_users": logged_in_users,
            "users": parsed_data
        }

    def _parse_serial_response(self, response, data=None):
        serial_settings = {}
        index = 16
        # If data is not provided, use an empty byte string
        data = data or b''
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get('SER#', {}).get(tag, f"unknown_tag_{tag}")
            if tag == 2:
                serial_settings[tag_name] = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
            else:
                serial_settings[tag_name] = struct.unpack('B', response[index:index + 1])[0]
                index += 1

        return serial_settings

    def _parse_network_info_response(self, response):
        strings = response[16:].split(b'\x00')
        # Skipping tag bytes...
        ip_address = strings[0][1:].decode('ascii')
        subnet_mask = strings[1][1:].decode('ascii')
        gateway_address = strings[2][1:].decode('ascii')
        host_name = strings[3][1:].decode('ascii')
        mac_address = strings[4][1:].decode('ascii')
        listening_port = int.from_bytes(strings[5][1:], 'big')

        return {
            "ip_address": ip_address,
            "subnet_mask": subnet_mask,
            "gateway_address": gateway_address,
            "host_name": host_name,
            "mac_address": mac_address,
            "listening_port": listening_port,
        }
    
    def _parse_datetime_response(self, response):
        
        year = int.from_bytes(response[17:19], 'big')
        month = int.from_bytes(response[20:21], 'big')
        day = int.from_bytes(response[22:23], 'big')
        hours = int.from_bytes(response[24:25], 'big')
        minutes = int.from_bytes(response[26:27], 'big')
        seconds = int.from_bytes(response[28:29], 'big')

        return {
            "year": year,
            "month": month,
            "day": day,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
        }
    
    def _parse_product_info_response(self, response):
        product_info = {}
        strings = response[16:].split(b'\x00', 16)[:-1]
        for string in range(len(strings)):
            tag = strings[string][0]
            tag_name = TAG_PARSER.get('SMGR', {}).get('INFO', {}).get(tag, f"unknown_tag_{tag}")
            product_info[tag_name] = strings[string][1:].decode('ascii')

        index = sum((len(s) + 2) for s in strings[:16])  # +1 for each null character and +1 for each tag
        while index < len(response):
            tag = response[index]
            index += 1
            tag_name = TAG_PARSER.get('SMGR', {}).get('INFO', {}).get(tag, f"unknown_tag_{tag}")
            if tag < 82:
                product_info[tag_name] = struct.unpack('>d', response[index:index + 8])[0]
                index += 8
            else:
                product_info[tag_name] = struct.unpack('>f', response[index:index + 4])[0]
                index += 4        
    
        return product_info
    
    def _parse_system_uptime_response(self, response):
        uptime = struct.unpack('>f', response[17:21])[0]
        app_uptime = struct.unpack('>f', response[22:26])[0]
        system_load = struct.unpack('>f', response[27:31])[0]

        return {
            "uptime": uptime,
            "app_uptime": app_uptime,
            "system_load": system_load,
        }
    
    def _parse_system_temperature_response(self, response):
        board_temp = struct.unpack('>f', response[17:21])[0]
        sensor_temp = struct.unpack('>f', response[22:26])[0]
        sensor_temp_derivative = struct.unpack('>f', response[27:31])[0]
        conf_min_temp = struct.unpack('>f', response[32:36])[0]
        conf_max_temp = struct.unpack('>f', response[37:41])[0]

        # The response gives this value twice due to a bug in the API
        # conf_max_temp_2 = struct.unpack('>f', response[42:46])[0] 
        fpga_temp = struct.unpack('>f', response[47:51])[0]

        return {
            "board_temp": board_temp,
            "sensor_temp": sensor_temp,
            "sensor_temp_derivative": sensor_temp_derivative,
            "conf_min_temp": conf_min_temp,
            "conf_max_temp": conf_max_temp,
            # "conf_max_temp_2": conf_max_temp_2,
            "fpga_temp": fpga_temp,
        }
    
    def _parse_list_snmp_trap_receivers_response(self, response):
        strings = response[16:].split(b'\x00')
        trap_ip_address = strings[0][1:].decode('ascii')
        trap_port = int.from_bytes(response[-2:], 'big')

        return {
            "trap_ip_address": trap_ip_address,
            "trap_port": trap_port,
        }
    
    def _parse_snmp_config_response(self, response):
        agent_port = int.from_bytes(response[-2:], 'big')

        return {
            "agent_port": agent_port,
        }
    
    def _parse_smgr_inst_response(self, response):
        snmp_installed = bool.from_bytes(response[17:18])
        obsolete_installed = bool.from_bytes(response[19:20])

        return {
            "snmp_installed": snmp_installed,
            "obsolete_installed": obsolete_installed,
        }
    
    ###################################################################
    ## Pulse frequency control API function parsers                  ##
    ## For reference, see Wistom API documentation (document 100051) ##
    ###################################################################
    
    def _parse_frequency_regulator_values(self, response):
        index = 16
        frequency_regulator_values = {}
        while index < len(response):
            tag = response[index]
            index +=1
            tag_name = TAG_PARSER.get('PULF', {}).get('REGV', {}).get(tag, f"unknown_tag_{tag}")
            frequency_regulator_values[tag_name] = struct.unpack('>d', response[index:index + 8])[0]
            index += 8
        return frequency_regulator_values

    ###################################################################
    ## Wistsense API function parsers                                ##
    ## For reference, see Wistom API documentation (document 100051) ##
    ###################################################################

    def _parse_wsns_data(self, response, data=None):
        print(data)
        spectrum_data = {}
        index = 16
        if data == None:
            while index < len(response):
                tag = response[index]
                index += 1

                tag_name = TAG_PARSER.get('WSNS', {}).get('DATA', {}).get(tag, f"unknown_tag_{tag}")
                value = response[index]
                spectrum_data[tag_name] = bool(value)
                index +=1
            return spectrum_data
        else:
            match data[1]:
                case 1: # Sensor spectrum
                    spectrum_data_values = []
                    tag = response[index]
                    index += 1
                    tag_name = TAG_PARSER.get('WSNS', {}).get('DATA', {}).get(tag, f"unknown_tag_{tag}")
                    spectrum_data_length = struct.unpack('>I', response[index:index + 4])[0]
                    index += 4
                    for value in range(spectrum_data_length):
                        spectrum_value = struct.unpack('>f', response[index:index + 4])[0]
                        spectrum_data_values.append(spectrum_value)
                        index += 4
                    spectrum_data = {
                        "spectrum_data_length": spectrum_data_length,
                        "spectrum_data_values": spectrum_data_values,
                    }
                case 2: # Wavelength reference spectrum
                    spectrum_data_values = []
                    tag = response[index]
                    index += 1
                    tag_name = TAG_PARSER.get('WSNS', {}).get('DATA', {}).get(tag, f"unknown_tag_{tag}")
                    spectrum_data_length = struct.unpack('>I', response[index:index + 4])[0]
                    index += 4
                    for value in range(spectrum_data_length):
                        spectrum_value = struct.unpack('>f', response[index:index + 4])[0]
                        spectrum_data_values.append(spectrum_value)
                        index += 4
                    spectrum_data = {
                        "spectrum_data_length": spectrum_data_length,
                        "spectrum_data_values": spectrum_data_values,
                    }
                case 3: # Interferometer spectrum
                    spectrum_data_values = []
                    tag = response[index]
                    index += 1
                    tag_name = TAG_PARSER.get('WSNS', {}).get('DATA', {}).get(tag, f"unknown_tag_{tag}")
                    spectrum_data_length = struct.unpack('>I', response[index:index + 4])[0]
                    index += 4
                    for value in range(spectrum_data_length):
                        spectrum_value = struct.unpack('>f', response[index:index + 4])[0]
                        spectrum_data_values.append(spectrum_value)
                        index += 4
                    spectrum_data = {
                        "spectrum_data_length": spectrum_data_length,
                        "spectrum_data_values": spectrum_data_values,
                    }
                case 4: # White light spectrum
                    spectrum_data_values = []
                    tag = response[index]
                    index += 1
                    tag_name = TAG_PARSER.get('WSNS', {}).get('DATA', {}).get(tag, f"unknown_tag_{tag}")
                    spectrum_data_length = struct.unpack('>I', response[index:index + 4])[0]
                    index += 4
                    for value in range(spectrum_data_length):
                        spectrum_value = struct.unpack('>f', response[index:index + 4])[0]
                        spectrum_data_values.append(spectrum_value)
                        index += 4
                    spectrum_data = {
                        "spectrum_data_length": spectrum_data_length,
                        "spectrum_data_values": spectrum_data_values,
                    }
                case 5: # Frequency scale
                    spectrum_data_values = []
                    tag = response[index]
                    index += 1
                    tag_name = TAG_PARSER.get('WSNS', {}).get('DATA', {}).get(tag, f"unknown_tag_{tag}")
                    spectrum_data_length = struct.unpack('>I', response[index:index + 4])[0]
                    index += 4
                    for value in range(spectrum_data_length):
                        spectrum_value = struct.unpack('>f', response[index:index + 4])[0]
                        spectrum_data_values.append(spectrum_value)
                        index += 4
                    spectrum_data = {
                        "spectrum_data_length": spectrum_data_length,
                        "spectrum_data_values": spectrum_data_values,
                    }
            return spectrum_data   
         
        
    def _parse_wsns_port(self, response):
        sensor_ports = {}
        index = 16 # start after header
        while index < len(response):
            port_tag = response[index]
            index += 1

            tag_name = TAG_PARSER.get('WSNS', {}).get('PORT', {}).get(port_tag, f"unknown_port_{port_tag}")
            type_name = PORT_TYPE.get(response[index], f"Unknown")
            sensor_ports[tag_name] = type_name
            index += 1

        return sensor_ports            

    def _parse_wsns_next(self, response):
        peak_frequencies_ports = {}
        peak_widths_ports = {}
        peak_amplitudes_ports = {}
        index = 16 # Start after header

        # Tag 101-116 (Frequency of each peak in spectrum, one spectrum per port)
        # Tag 151-166 (FWHM of each peak)
        # Tag 201-216 (Amplitudes of each peak)
        # First value after each tag is the number of peaks.

        while index < len(response):
            port_tag = response[index]

            if port_tag == 7: # Tag 7, 3, 4, 5, 6 comes after peak data in this order and is parsed differently
                break
            index += 1

            # Resolve port_tag to its string representation using TAG_PARSER in wistomconstants
            tag_name = TAG_PARSER.get('WSNS', {}).get('NEXT', {}).get(port_tag, f"unknown_tag_{port_tag}")

            # Handle peak widths (151-166)
            if 151 <= port_tag <= 166:
                number_of_peak_widths = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                peak_widths = []
                for _ in range(number_of_peak_widths):
                    peak_width = struct.unpack('>d', response[index:index + 8])[0]
                    peak_widths.append(peak_width)
                    index += 8
                peak_widths_ports[tag_name] = {
                    "number_of_peaks": number_of_peak_widths,
                    "peak_widths": peak_widths,
                }
                continue

            # Handle peak amplitudes (201-216)
            if 201 <= port_tag <= 216:
                number_of_peak_amplitudes = struct.unpack('>I', response[index:index + 4])[0]
                index += 4
                peak_amplitudes = []
                for _ in range(number_of_peak_amplitudes):
                    peak_amplitude = struct.unpack('>d', response[index:index + 8])[0]
                    peak_amplitudes.append(peak_amplitude)
                    index += 8
                peak_amplitudes_ports[tag_name] = {
                    "number_of_peaks": number_of_peak_amplitudes,
                    "peak_amplitudes": peak_amplitudes,
                }
                continue

            # Read the number of peaks (UINT32)
            number_of_frequency_peaks = struct.unpack('>I', response[index:index + 4])[0]
            index += 4

            # Read the peak frequencies for the port
            peak_frequencies = []
            for _ in range(number_of_frequency_peaks):
                peak_frequency = struct.unpack('>d', response[index:index + 8])[0]
                peak_frequencies.append(peak_frequency)
                index += 8

            peak_frequencies_ports[tag_name] = {
                "number_of_peaks": number_of_frequency_peaks,
                "peak_frequencies": peak_frequencies,
            }


        calibration_data = {}
        
        # Tag 7, 3, 4, 5, 6 are used for calibration and error correction (?)

        # Tag 7: Frequency errors
        while index < len(response):
            tag = response[index]
            if tag == 3:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get('NEXT', {}).get(tag, f"unknown_tag_{tag}")
            number_of_frequency_errors = struct.unpack('>I', response[index:index + 4])[0]
            index += 4

            frequency_errors = []
            for _ in range(number_of_frequency_errors):
                frequency_error = struct.unpack('>d', response[index:index + 8])[0]
                frequency_errors.append(frequency_error)
                index += 8

        
        
        # Tag 3-6 (linear fit equation and other data for calibration and error-correcting)
        
        # Tag 3 & 4 (linear fits)
        while index < len(response):
            tag = response[index]
            if tag == 5:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get('NEXT', {}).get(tag, f"unknown_tag_{tag}")
            calibration_data[tag_name] = None 
            calibration_data[tag_name] = {
                'slope': struct.unpack('>d', response[index:index + 8])[0],
                'intercept': struct.unpack('>d', response[index + 8:index + 16])[0],
                'r_value': struct.unpack('>d', response[index + 16:index + 24])[0]
                }
            index += 24

        # Tag 5 (number of reference lines & zero-crossings)
        tag = response[index]
        index +=1
        tag_name = TAG_PARSER.get('WSNS', {}).get('NEXT', {}).get(tag, f"unknown_tag_{tag}")
        calibration_data[tag_name] = {
            'reference_lines': struct.unpack('>I', response[index:index + 4])[0],
            'zero_crossings': struct.unpack('>I', response[index + 4: index + 8])[0]
        }
        index += 8
        
        # tag 6 first and last crossing

        tag = response[index]
        index +=1
        tag_name = TAG_PARSER.get('WSNS', {}).get('NEXT', {}).get(tag, f"unknown_tag_{tag}")
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
    
    # There are bugs in the code and mistakes in the documentation for WSNS PARA.
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
            tag_name = TAG_PARSER.get('WSNS', {}).get('PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack('>B', response[index:index + 1])[0]
            index += 1
        # Tags 2-6 (FLOAT64 values)
        while index < len(response):
            tag = response[index]
            if tag == 7:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get('PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack('>d', response[index:index + 8])[0]
            index += 8

        # Tags 7-8 (UINT32)
        while index < len(response):
            tag = response[index]
            if tag == 101:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get('PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack('>I', response[index:index + 4])[0]
            index += 4

        #Tag 101-150 (sensor port thresholds, FLOAT64)
        while index < len(response):
            tag = response[index]
            if tag == 9:
                break
            index += 1
            tag_name = TAG_PARSER.get('WSNS', {}).get('PARA', {}).get(tag, f"unknown_tag_{tag}")
            wistsense_parameters[tag_name] = struct.unpack('>d', response[index:index + 8])[0]
            index +=8
        
        return wistsense_parameters

if __name__ == "__main__":

    print(f"Connecting to {HOST}:{PORT}")
    with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
        login_response = client.login()
        print("Login Response:", login_response)
        client.custom_api_request(COMMAND_ID['GET'], b'WSNS', b'NEXT', b'')

        if login_response.get("command_id") == 'LOGINIRES':
            network_info = client.get_smgr_network_info()
            print("Network Info:", network_info)