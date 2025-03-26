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
    def login(self):
        # payload = self.__create_login_payload()
        cid = COMMAND_ID['LOGIN']
        app_id = b'LGIN'
        op_id = b'API2'
        user_id_bytes = self.user_id.encode('ascii')
        password_bytes = self.password.encode('ascii')
        data = (user_id_bytes + b'\x00' 
                   + password_bytes + b'\x00')
        response = self.__send_request(cid, app_id, op_id, data)
        return self._parse_login_response(response)
    


    ## Helper methods
    def __send_request(self, payload):
        if not self.socket:
            raise ConnectionError("Not connected to server")
        self.socket.sendall(payload)
        response = self.socket.recv(4096) ## Test all possible Wistom API requests
        return response
    
    def __increment_token(self):
        self.token += 1
        return self.token
    
    ## Private methods

    ## Creates the login payload as described in Page 74 Table 11-2
    ## of the Wistom User Guide
    def __create_login_payload(self):
        user_id_bytes = self.user_id.encode('ascii')
        password_bytes = self.password.encode('ascii')
        payload_length = (len(user_id_bytes) 
                          + len(password_bytes) 
                          + 2) # add two bytes for the null-terminators
        payload = (user_id_bytes + b'\x00' 
                   + password_bytes + b'\x00')
        return (
            COMMAND_ID['LOGIN']
            + self.token.to_bytes(2, 'big')
            + b'LGIN'
            + b'API2'
            + payload_length.to_bytes(4, 'big')
            + payload
        )
    
    ## Parses the login response into a human-readable format
    def __parse_login_response(self, response):
        command_id = response[0:2]
        token = int.from_bytes(response[2:4], 'big')
        payload_length = int.from_bytes(response[12:16], 'big')
        login_result = response[16:16 + payload_length]

        command_name = next((key for key, value in COMMAND_ID.items() if value == command_id), "Unknown Command")
        login_result_name = next((key for key, value in LOGIN_RESULT.items() if value == login_result), "Unknown Login Result")

        return {
            "command_id": command_name,
            "token": token,
            "login_result": login_result_name
        }

if __name__ == "__main__":

    print(f"Connecting to {HOST}:{PORT}")
    with WistomClient(HOST, PORT, USER_ID, PASSWORD) as client:
        login_response = client.login()
        print("Login Response:", login_response)

        if login_response.get("command_id") == 'LOGINIRES':
            network_info = client.get_network_info()
            print("Network Info:", network_info)