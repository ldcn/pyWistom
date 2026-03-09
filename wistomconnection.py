import socket
from sshtunnel import SSHTunnelForwarder
from wistomconfig import SSH_HOST, SSH_PORT


class WistomConnection:
    def __init__(self, host, port, use_ssh=False, user_id=None, password=None):
        self.host = host
        self.port = port
        self.socket = None
        self.token = 0
        self.use_ssh = use_ssh
        self.ssh_user = user_id
        self.ssh_password = password
        self.ssh_tunnel = None

    def _create_ssh_tunnel(self):
        self.ssh_tunnel = SSHTunnelForwarder(
            (SSH_HOST, SSH_PORT),
            ssh_username=self.ssh_user,
            ssh_password=self.ssh_password,
            remote_bind_address=('localhost', self.port),
            compression=False,
            set_keepalive=0
        )
        self.ssh_tunnel.start()
        return self.ssh_tunnel.local_bind_port

    def connect(self):
        if self.use_ssh:
            local_port = self._create_ssh_tunnel()
            connect_host = 'localhost'
            connect_port = local_port
        else:
            connect_host = self.host
            connect_port = self.port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.connect((connect_host, connect_port))

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.socket = None
        if self.ssh_tunnel:
            self.ssh_tunnel.stop()
            self.ssh_tunnel = None

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
