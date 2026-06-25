HOST = "0.0.0.0"
PORT = 8765
MAX_CONNECTIONS = 50

TIMEOUTS = {
    "accept": 1,
    "socket_select": 1,
    "client_connect": 10,
    "disconnect_timer": 30,
}
