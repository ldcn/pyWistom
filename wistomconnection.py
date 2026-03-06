import socket
import struct
import threading
import logging
import time
from queue import Queue, Empty
from sshtunnel import SSHTunnelForwarder
from wistomconstants import COMMAND_ID, ALARM_ID


logger = logging.getLogger(__name__)


# All known alarm command IDs for quick lookup
_ALARM_CMD_IDS = set(ALARM_ID.values())


class WistomConnection:
    """Low-level socket connection to a Wistom device.

    Supports two operating modes:

    * **Synchronous** (default, ``threaded=False``): The caller reads
      responses directly from the socket via :meth:`recv_message`.
      This preserves backward compatibility with existing code.

    * **Threaded** (``threaded=True``): A dedicated receiver thread
      continuously reads messages from the socket, dispatching API
      responses to per-token queues and alarm messages to registered
      alarm listeners.  Use :meth:`send_and_receive` for synchronous
      request/response and :meth:`send` + callbacks for async
      patterns.
    """

    def __init__(self, host, port, use_ssh=False, user_id=None,
                 password=None, threaded=False, ssh_host=None,
                 ssh_port=22):
        self.host = host
        self.port = port
        self.ssh_host = ssh_host or host
        self.ssh_port = ssh_port
        self.socket = None
        self.token = 0
        self.use_ssh = use_ssh
        self.ssh_user = user_id
        self.ssh_password = password
        self.ssh_tunnel = None

        # Threaded receiver support
        self.threaded = threaded
        self._receiver_thread = None
        self._running = False
        self._lock = threading.Lock()

        # Token-based response correlation:
        # Maps token -> Queue that will receive exactly one response.
        self._pending_requests = {}
        self._pending_lock = threading.Lock()

        # Alarm listeners: list of callables(alarm_msg_dict)
        self._alarm_listeners = []
        self._alarm_lock = threading.Lock()

        # Connection state listeners: list of callables(connected: bool)
        self._connection_listeners = []

    # ------------------------------------------------------------------
    # SSH tunnelling
    # ------------------------------------------------------------------

    def _create_ssh_tunnel(self):
        self.ssh_tunnel = SSHTunnelForwarder(
            (self.ssh_host, self.ssh_port),
            ssh_username=self.ssh_user,
            ssh_password=self.ssh_password,
            remote_bind_address=('localhost', self.port),
            compression=False,
            set_keepalive=0
        )
        self.ssh_tunnel.start()
        return self.ssh_tunnel.local_bind_port

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------

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

        # Do NOT start receiver here; login() uses synchronous recv.
        # Call start_receiver() after login completes.

    def disconnect(self):
        self._stop_receiver()
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()
            self.socket = None
        if self.ssh_tunnel:
            self.ssh_tunnel.stop()
            self.ssh_tunnel = None
        # Wake up any threads waiting on pending requests
        with self._pending_lock:
            for token, q in self._pending_requests.items():
                q.put(None)
            self._pending_requests.clear()

    # ------------------------------------------------------------------
    # Login (synchronous, before receiver thread for threaded mode)
    # ------------------------------------------------------------------

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
        # Login always uses synchronous recv (even in threaded mode,
        # receiver thread is started after login completes).
        response = self._recv_message_raw()

        # Now safe to start the receiver thread (login response consumed)
        if self.threaded and not (
                self._receiver_thread
                and self._receiver_thread.is_alive()):
            self._start_receiver()

        return response

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def increment_token(self):
        with self._lock:
            self.token = (self.token + 1) & 0xFFFF
        return self.token

    def get_token(self):
        return self.token

    # ------------------------------------------------------------------
    # Raw socket I/O helpers
    # ------------------------------------------------------------------

    def _recv_exact(self, n):
        """Read exactly *n* bytes from the socket."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self.socket.recv(n - len(buf))
            if not chunk:
                raise ConnectionError(
                    "Connection closed while reading from socket")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_message_raw(self):
        """Read one complete message (header + payload) from the socket.

        Returns the full raw bytes including the 16-byte header for
        standard API messages.  For alarm messages (8-byte header) the
        returned bytes start with the alarm cmd_id.
        """
        # Peek at the first 2 bytes to determine message type
        header_start = self._recv_exact(2)
        cmd_id = header_start

        if cmd_id in _ALARM_CMD_IDS:
            # Alarm messages: cmd_id(2) + token(2) + data_size(4) = 8 bytes
            rest_of_header = self._recv_exact(6)  # token(2) + data_size(4)
            header = header_start + rest_of_header
            data_size = struct.unpack('>I', header[4:8])[0]
            if data_size > 0:
                payload = self._recv_exact(data_size)
            else:
                payload = b''
            return header + payload
        else:
            # Standard API messages: cmd_id(2) + token(2) + app_id(4) +
            #   op_id(4) + data_size(4) = 16 bytes
            rest_of_header = self._recv_exact(14)
            header = header_start + rest_of_header
            data_size = struct.unpack('>I', header[12:16])[0]
            if data_size > 0:
                payload = self._recv_exact(data_size)
            else:
                payload = b''
            return header + payload

    def send_raw(self, payload):
        """Send raw bytes over the socket."""
        if not self.socket:
            raise ConnectionError("Not connected to server")
        self.socket.sendall(payload)

    # ------------------------------------------------------------------
    # Threaded receiver
    # ------------------------------------------------------------------

    def _start_receiver(self):
        if self._receiver_thread and self._receiver_thread.is_alive():
            return
        self._running = True
        self._receiver_thread = threading.Thread(
            target=self._receiver_loop, daemon=True,
            name="WistomReceiver")
        self._receiver_thread.start()

    def _stop_receiver(self):
        self._running = False
        if self._receiver_thread and self._receiver_thread.is_alive():
            self._receiver_thread.join(timeout=3.0)
        self._receiver_thread = None

    def _receiver_loop(self):
        """Continuously read messages and dispatch them."""
        while self._running:
            try:
                msg = self._recv_message_raw()
            except (ConnectionError, OSError) as exc:
                if self._running:
                    logger.warning("Receiver thread: connection lost: %s", exc)
                    self._fire_connection_lost()
                break

            cmd_id = msg[0:2]
            if cmd_id in _ALARM_CMD_IDS:
                self._dispatch_alarm(msg)
            else:
                token = struct.unpack('>H', msg[2:4])[0]
                self._dispatch_response(token, msg)

    def _dispatch_response(self, token, msg):
        """Route an API response to the waiting caller by token."""
        with self._pending_lock:
            q = self._pending_requests.pop(token, None)
        if q is not None:
            q.put(msg)
        else:
            logger.debug(
                "Received response for unknown token %d, discarding", token)

    def _dispatch_alarm(self, msg):
        """Fire alarm message to all registered listeners."""
        with self._alarm_lock:
            listeners = list(self._alarm_listeners)
        for listener in listeners:
            try:
                listener(msg)
            except Exception:
                logger.exception("Alarm listener raised an exception")

    def _fire_connection_lost(self):
        """Notify connection listeners that the connection was lost."""
        for listener in self._connection_listeners:
            try:
                listener(False)
            except Exception:
                logger.exception("Connection listener raised an exception")

    # ------------------------------------------------------------------
    # Threaded send / receive API
    # ------------------------------------------------------------------

    def send_and_receive(self, payload, token, timeout=5.0):
        """Send a request and wait for the response with matching token.

        This is the primary method for synchronous request/response in
        threaded mode.  The receiver thread routes the response back
        via the token-keyed queue.

        :param payload: Complete message bytes to send (header + data).
        :param token: The token value embedded in the request.
        :param timeout: Seconds to wait for a response.
        :returns: Raw response bytes.
        :raises TimeoutError: If no response arrives within *timeout*.
        :raises ConnectionError: If not connected.
        """
        q = Queue(maxsize=1)
        with self._pending_lock:
            self._pending_requests[token] = q
        try:
            self.send_raw(payload)
            response = q.get(timeout=timeout)
            if response is None:
                raise ConnectionError("Connection was closed")
            return response
        except Empty:
            with self._pending_lock:
                self._pending_requests.pop(token, None)
            raise TimeoutError(
                f"Request timed out after {timeout} seconds (token={token})")

    # ------------------------------------------------------------------
    # Alarm listener management
    # ------------------------------------------------------------------

    def add_alarm_listener(self, callback):
        """Register a callable to receive alarm messages.

        :param callback: ``callback(raw_alarm_bytes)`` — called from the
            receiver thread.  Must be thread-safe.
        """
        with self._alarm_lock:
            if callback not in self._alarm_listeners:
                self._alarm_listeners.append(callback)

    def remove_alarm_listener(self, callback):
        """Unregister a previously registered alarm listener."""
        with self._alarm_lock:
            try:
                self._alarm_listeners.remove(callback)
            except ValueError:
                pass

    def add_connection_listener(self, callback):
        """Register a callable to be notified of connection state changes.

        :param callback: ``callback(connected: bool)``
        """
        if callback not in self._connection_listeners:
            self._connection_listeners.append(callback)

    def remove_connection_listener(self, callback):
        """Unregister a connection listener."""
        try:
            self._connection_listeners.remove(callback)
        except ValueError:
            pass
