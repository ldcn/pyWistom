"""
Connection management for Wistom devices.

Handles TCP socket connections with optional SSH tunneling for
remote access to Wistom fiber optic sensing devices.
"""
import socket
from sshtunnel import SSHTunnelForwarder
from wistomconfig import SSH_HOST, SSH_PORT


class WistomConnection:
    """
    Manages TCP/SSH connections to Wistom devices.

    Handles connection establishment, authentication, and message
    token management for the Wistom binary protocol.

    :param host: Device IP address or hostname
    :type host: str
    :param port: TCP port number
    :type port: int
    :param use_ssh: Enable SSH tunneling
    :type use_ssh: bool
    :param user_id: SSH/API username
    :type user_id: str
    :param password: SSH/API password
    :type password: str
    """

    def __init__(self, host, port, use_ssh=False, user_id=None, password=None):
        """Initialize connection parameters."""
        self.host = host
        self.port = port
        self.socket = None
        self.token = 0
        self.use_ssh = use_ssh
        self.ssh_user = user_id
        self.ssh_password = password
        self.ssh_tunnel = None

    def _create_ssh_tunnel(self):
        """Create SSH tunnel to remote device and return local port."""
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
        """Establish TCP connection to device, optionally via SSH tunnel."""
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
        """Close socket and SSH tunnel if active."""
        if self.socket:
            self.socket.close()
            self.socket = None
        if self.ssh_tunnel:
            self.ssh_tunnel.stop()
            self.ssh_tunnel = None

    def login(self, user_id, password, command_id, app_id, op_id):
        """
        Send login request to authenticate with the device.

        :param user_id: Username for authentication
        :param password: Password for authentication
        :param command_id: Protocol command identifier
        :param app_id: Application identifier (4 bytes)
        :param op_id: Operation identifier (4 bytes)
        :returns: Raw response bytes from device
        """
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
        """Increment and return the message token for request sequencing."""
        self.token += 1
        return self.token

    def get_token(self):
        """Return the current message token value."""
        return self.token
