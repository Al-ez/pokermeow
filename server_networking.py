import select
import socket
import threading

from config import TIMEOUTS
from network_protocol import ProtocolError, recv_json, send_json


def local_ipv4_addresses():
    """Return non-loopback IPv4 addresses advertised by the local host."""
    addresses = []
    try:
        hostname = socket.gethostname()
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = result[4][0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
    except OSError:
        pass
    return addresses


class ClientConnection:
    """Server-side JSON transport with no poker or lobby decisions."""

    def __init__(self, socket_obj, address, shutdown_event=None):
        self.socket = socket_obj
        self.address = address
        self.file = socket_obj.makefile("rw", encoding="utf-8", newline="\n")
        self.name = None
        self.buy_in = None
        self.connected = True
        self.leave_after_hand = False
        self.shutdown_event = shutdown_event or threading.Event()
        self.send_lock = threading.Lock()

    def send(self, message):
        if not self.connected:
            raise ConnectionError("Client is disconnected")
        try:
            with self.send_lock:
                send_json(self.file, message)
        except OSError as error:
            self.connected = False
            raise ConnectionError("Client is disconnected") from error

    def recv(self, stop_event=None):
        if not self.connected:
            return None
        while not self.shutdown_event.is_set():
            if stop_event is not None and stop_event.is_set():
                return None
            try:
                readable, _, _ = select.select(
                    [self.socket], [], [], TIMEOUTS["socket_select"]
                )
            except (OSError, ValueError):
                self.connected = False
                return None
            if not readable:
                continue
            try:
                message = recv_json(self.file)
            except socket.timeout:
                continue
            except (ProtocolError, ConnectionResetError, OSError):
                self.connected = False
                return None
            if message is None:
                self.connected = False
            return message
        self.connected = False
        return None

    def force_close(self):
        self.connected = False
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.file.close()
        except OSError:
            pass
        try:
            self.socket.close()
        except OSError:
            pass

    def set_timeout(self, timeout):
        self.socket.settimeout(timeout)

    def close(self):
        self.connected = False
        try:
            self.file.close()
        except OSError:
            pass
        try:
            self.socket.close()
        except OSError:
            pass
