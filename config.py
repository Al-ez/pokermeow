HOST = "0.0.0.0"
PORT = 8765
MAX_CONNECTIONS = 50

# Display mode switch for the GUI:
# False = fixed 1180x720 window for development/testing.
# True = borderless fullscreen layout for playing.
FULLSCREEN = False
WINDOWED_SIZE = (1180, 720)

TIMEOUTS = {
    "accept": 1,
    "socket_select": 1,
    "client_connect": 10,
    "disconnect_timer": 30,
    "rebuy": 30,
    "run_it_vote": 5,
    "showdown_display": 3,
}
