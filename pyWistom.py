import socket
import struct

from wistomconstants import *
from wistomconfig import HOST, PORT, USER_ID, PASSWORD

# Not yet implemented, for future-proofing
from wistomconfig import API_VERSION

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
    
    def custom_api_request(self, command_id, app_id, op_id, data):
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
        
        if cid == COMMAND_ID["GETRES"]:
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
      
        return response[16:].hex()

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
    
    def _parse_setnack_header(self, response):
        token = int.from_bytes(response[2:4], 'big')
        app_id = response[4:8].decode('ascii')
        op_id = response[8:12].decode('ascii')
        error_code = response[-2:]
        tag_number = response[-4:-2]
        
        return {
            "SET Not acknowledged": f"{app_id} {op_id}",
            "Token": f"{token}",
            "Error": ERROR_CODE[error_code],
            "Tag number": int.from_bytes(tag_number, 'big') if tag_number != b'\x00\x00' else None
        } 

    def _parse_smgr_info_response(self, response):
        header = {"cid": response[0:2].hex(),
                  "token": int.from_bytes(response[2:4], 'big'),
                  "app_id": response[4:8].decode('ascii'),
                  "op_id": response[8:12].decode('ascii'),
                  "data_length": int.from_bytes(response[12:16], 'big'),
        }

        strings = response[16:].split(b'\x00')
        # Skipping tag bytes (might need to change this later)
        hw_product_number = strings[0][1:].decode('ascii')
        hw_id_number = strings[1][1:].decode('ascii')
        hw_revision = strings[2][1:].decode('ascii')
        hw_serial_number = strings[3][1:].decode('ascii')
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

        start_index = sum(len(s) + 1 for s in strings[:16])  # +1 for each null character

        start_calib_freq = struct.unpack('>d', response[start_index + 1:start_index + 9])[0]  # FLOAT64
        end_calib_freq = struct.unpack('>d', response[start_index + 10:start_index + 18])[0]  # FLOAT64
        start_temp_calib = struct.unpack('>f', response[start_index + 19:start_index + 23])[0]  # FLOAT32
        end_temp_calib = struct.unpack('>f', response[start_index + 24:start_index + 28])[0]  # FLOAT32

        return {
            "hw_product_number": hw_product_number,
            "hw_id_number": hw_id_number,
            "hw_revision": hw_revision,
            "hw_serial_number": hw_serial_number,
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
            "start_calib_freq": start_calib_freq,
            "end_calib_freq": end_calib_freq,
            "start_temp_calib": start_temp_calib,
            "end_temp_calib": end_temp_calib,
        }

if __name__ == "__main__":

    print(f"Connecting to {HOST}:{PORT}")
    with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
        login_response = client.login()
        print("Login Response:", login_response)

        if login_response.get("command_id") == 'LOGINIRES':
            network_info = client.get_network_info()
            print("Network Info:", network_info)