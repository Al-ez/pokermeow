import socket
import threading

from config import TIMEOUTS
from network_protocol import ProtocolError, recv_json, send_json


class JsonConnection:
    """Threaded JSON transport. It deliberately contains no game decisions."""

    def __init__(self, on_message, on_disconnect):
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._socket = None
        self._file = None
        self._reader = None
        self._send_lock = threading.Lock()
        self._closed = threading.Event()

    @property
    def connected(self):
        return self._socket is not None and not self._closed.is_set()

    def connect(self, host, port):
        if self.connected:
            raise RuntimeError("Already connected")

        socket_obj = socket.create_connection(
            (host, port),
            timeout=TIMEOUTS["client_connect"],
        )
        socket_obj.settimeout(None)
        self._socket = socket_obj
        self._file = socket_obj.makefile("rw", encoding="utf-8", newline="\n")
        self._closed.clear()
        self._reader = threading.Thread(
            target=self._read_messages,
            name="PokerMeow network reader",
            daemon=True,
        )
        self._reader.start()

    def send(self, message):
        if not self.connected or self._file is None:
            raise ConnectionError("Not connected")

        with self._send_lock:
            send_json(self._file, message)

    def close(self):
        if self._closed.is_set():
            return

        self._closed.set()
        socket_obj = self._socket
        file_obj = self._file
        self._socket = None
        self._file = None
        if socket_obj is not None:
            try:
                socket_obj.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            socket_obj.close()
        if file_obj is not None:
            try:
                file_obj.close()
            except OSError:
                pass

    def _read_messages(self):
        reason = "Disconnected from server."
        try:
            while not self._closed.is_set():
                message = recv_json(self._file)
                if message is None:
                    break
                self._on_message(message)
        except ProtocolError as error:
            reason = f"Server sent an invalid message: {error}"
        except (ConnectionError, OSError, ValueError) as error:
            if not self._closed.is_set():
                reason = f"Connection lost: {error}"
        finally:
            was_open = not self._closed.is_set()
            self.close()
            if was_open:
                self._on_disconnect(reason)
