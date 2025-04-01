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

class WistomClient:
    def __init__(self, host, port, user_id, password):
        self.host = host
        self.port = port
        self.user_id = user_id
        self.password = password
        self.socket = None
        self.token = 0

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    ## Context manager methods
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, type, value, traceback):
        self.disconnect()

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
    def __send_request(self, cid, app_id, op_id, data):
        data_length = len(data)
        payload = (cid 
                   + self.token.to_bytes(2, 'big')
                   + app_id
                   + op_id
                   + data_length.to_bytes(4, 'big')
                   + data)
        if not self.socket:
            raise ConnectionError("Not connected to server")
        self.socket.sendall(payload)
        response = self.socket.recv(4096) ## Test all possible Wistom API requests
        return self.__handle_response(app_id, op_id, response)
    
    def __handle_response(self, app_id, op_id, response):
        cid = response[0:2]
        header_parser_name = RESPONSE_HEADER_PARSER.get(cid, "__parse_unknown_command")
        header_parser = getattr(self, header_parser_name, self.__parse_unknown_command)
        parsed_header = header_parser(response)
        
        if cid == (COMMAND_ID["GETRES"] or COMMAND_ID["LOGINRES"]):
            parser_name = RESPONSE_PARSER.get(app_id.decode('ascii'), {}).get(op_id.decode('ascii'), "_parse_unknown_response")
            parser = getattr(self, parser_name, self.__parse_unknown_response)
            parsed_response = parser(response)

            return {
                "header": parsed_header,
                "response": parsed_response,
            }
        else: return parsed_header
    
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

    def __parse_unknown_response(self, response):
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

        return {
            "GET Response": f"{app_id} {op_id}",
            "Token": f"{token}"
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

    def _parse_login_session_info_response(self, response):
        
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

    def _parse_serial_response(self, response):
        serial_settings = {}
        index = 16
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
        strings = response[16:].split(b'\x00', 16)[:-1]
        # Skipping tag bytes (might need to change this later)
        hardware_product_number = strings[0][1:].decode('ascii')
        hardware_id_number = strings[1][1:].decode('ascii')
        hardware_revision = strings[2][1:].decode('ascii')
        hardware_serial_number = strings[3][1:].decode('ascii')
        sensor_product_number = strings[4][1:].decode('ascii')
        sensor_id_number = strings[5][1:].decode('ascii')
        sensor_revision = strings[6][1:].decode('ascii')
        sensor_serial_number = strings[7][1:].decode('ascii')
        software_product_number = strings[8][1:].decode('ascii')
        software_revision = strings[9][1:].decode('ascii')
        firmware_revision = strings[10][1:].decode('ascii')
        pld_revision = strings[11][1:].decode('ascii')
        bootstrap_revision = strings[12][1:].decode('ascii')
        switch_software_revision = strings[13][1:].decode('ascii')
        unit_serial = strings[14][1:].decode('ascii')
        production_date = strings[15][1:].decode('ascii')

        start_index = sum((len(s) + 2) for s in strings[:16])  # +1 for each null character and +1 for each tag

        start_calibration_frequency = struct.unpack('>d', response[start_index + 1:start_index + 9])[0]
        end_calibration_frequency = struct.unpack('>d', response[start_index + 10:start_index + 18])[0]
        start_calibration_temperature = struct.unpack('>f', response[start_index + 19:start_index + 23])[0]
        end_calibration_temperature = struct.unpack('>f', response[start_index + 24:start_index + 28])[0]

        return {
            "hardware_product_number": hardware_product_number,
            "hardware_id_number": hardware_id_number,
            "hardware_revision": hardware_revision,
            "hardware_serial_number": hardware_serial_number,
            "sensor_product_number": sensor_product_number,
            "sensor_id_number": sensor_id_number,
            "sensor_revision": sensor_revision,
            "sensor_serial_number": sensor_serial_number,
            "software_product_number": software_product_number,
            "software_revision": software_revision,
            "firmware_revision": firmware_revision,
            "pld_revision": pld_revision,
            "bootstrap_revision": bootstrap_revision,
            "switch_software_revision": switch_software_revision,
            "unit_serial": unit_serial,
            "production_date": production_date,
            "start_calibration_frequency": start_calibration_frequency,
            "end_calibration_frequency": end_calibration_frequency,
            "start_calibration_temperature": start_calibration_temperature,
            "end_calibration_temperature": end_calibration_temperature,
        }
    
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
    ## Wistsense API function parsers                                ##
    ## For reference, see Wistom API documentation (document 100051) ##
    ###################################################################

    def _parse_wsns_data(self, response):
        spectrum_data = {}
        index = 16
        while index < len(response):
            tag = response[index]
            index += 1

            tag_name = TAG_PARSER.get('WSNS', {}).get('DATA', {}).get(tag, f"unknown_tag_{tag}")
            data = response[index]
            spectrum_data[tag_name] = bool(data)
            index +=1

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
        while index < len(response):
            port_tag = response[index]
            index += 1

            if port_tag == 7:  # after peaks, wild undocumented tag 7 appears...
                break

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

            ##################################################
            ##                                              ##
            ## Add the remaining tags (7, 3, 4, 5, 6) here! ##
            ##                                              ##
            ##################################################

        return {
            "peak_frequencies_ports": peak_frequencies_ports,
            "peak_widths_ports": peak_widths_ports,
            "peak_amplitudes_ports": peak_amplitudes_ports,
        }

if __name__ == "__main__":

    print(f"Connecting to {HOST}:{PORT}")
    with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
        login_response = client.login()
        print("Login Response:", login_response)
        client.custom_api_request(COMMAND_ID['GET'], b'WSNS', b'NEXT', b'')

        if login_response.get("command_id") == 'LOGINIRES':
            network_info = client.get_smgr_network_info()
            print("Network Info:", network_info)