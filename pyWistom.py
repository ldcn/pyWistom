import socket
from struct import unpack

from wistomconstants import *
from wistomconfig import HOST, PORT, USER_ID, PASSWORD, API_VERSION


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

    def send_request(self, payload):
        if not self.socket:
            raise ConnectionError("Not connected to server")
        self.socket.sendall(payload)
        response = self.socket.recv(4096)
        return response
    
    def increment_token(self):
        self.token += 1
        return self.token
    
    def login(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        self.increment_token()
        payload = self.__create_login_payload(self.user_id, self.password)
        response = self.send_request(payload)
        return self.__parse_login_response(response)
    

    ## Private methods

    ## Creates the login payload as described in Page 74 Table 11-2
    ## of the Wistom User Guide
    def __create_login_payload(self, user_id, password):
        user_id_bytes = user_id.encode('ascii')
        password_bytes = password.encode('ascii')
        payload_length = (len(user_id_bytes) 
                          + len(password_bytes) 
                          + 2) # add two bytes for the null-terminators
        payload = (user_id_bytes + b'\x00' 
                   + password_bytes + b'\x00')
        return (
            b'\x00\x01'  # Example command ID for login
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
    host_input = input("Wistom IP: ")
    host = host_input if host_input else HOST
    port_input = input(f"Port (default {PORT}): ")
    port = int(port_input) if port_input else PORT

    client = WistomClient(host, port)
    print(f"Connecting to {host}:{port}")
    try:
        client.connect()
        user_id_input = input("login as: ")
        password_input = input("Password: ")

        user_id = user_id_input if user_id_input else USER_ID
        password = password_input if password_input else PASSWORD

        login_response = client.login(user_id, password)
        print("Login Response:", login_response)

        if login_response.get("command_id") == 'LOGINIRES':
            network_info = client.get_network_info()
            print("Network Info:", network_info)

    except Exception as e:
        print(f"An error occured: {e}")
    finally:
        client.disconnect()