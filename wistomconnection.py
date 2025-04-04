import socket

class WistomConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.token = 0

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def login(self, user_id, password, command_id, app_id, op_id):
        user_id_bytes = user_id.encode('ascii')
        password_bytes = password.encode('ascii')
        data = user_id_bytes + b'\x00' + password_bytes + b'\x00'
        payload = (
            command_id
            + self.token.to_bytes(2, 'big')
            + app_id
            + op_id
            + len(data).to_bytes(4, 'big')
            + data
        )
        self.socket.sendall(payload)
        response = self.socket.recv(1024)
        return response
    
    def increment_token(self):
        self.token += 1
        return self.token

    def get_token(self):
        return self.token