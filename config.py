import os


def _environment_int(name, default, minimum=1):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a whole number") from error
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


HOST = os.getenv("POKERMEOW_HOST", "0.0.0.0")
PORT = _environment_int("POKERMEOW_PORT", 8765)
MAX_CONNECTIONS = _environment_int("POKERMEOW_MAX_CONNECTIONS", 50)

# Display mode switch for the GUI:
# False = fixed 1180x720 window for development/testing.
# True = borderless fullscreen layout for playing.
FULLSCREEN = False
WINDOWED_SIZE = (1180, 720)

TIMEOUTS = {
    "accept": _environment_int("POKERMEOW_ACCEPT_TIMEOUT", 1),
    "socket_select": _environment_int("POKERMEOW_SOCKET_SELECT_TIMEOUT", 1),
    "client_connect": _environment_int("POKERMEOW_CONNECT_TIMEOUT", 10),
    "disconnect_timer": _environment_int("POKERMEOW_DISCONNECT_TIMEOUT", 30),
    "rebuy": _environment_int("POKERMEOW_REBUY_TIMEOUT", 30),
    "run_it_vote": _environment_int("POKERMEOW_RUN_IT_TIMEOUT", 5),
    "showdown_display": _environment_int("POKERMEOW_SHOWDOWN_SECONDS", 3),
}
