from pokermeow_gui.controller import ClientController


class FakeConnection:
    instances = []

    def __init__(self, on_message, on_disconnect):
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.connected = False
        self.sent = []
        self.__class__.instances.append(self)

    def connect(self, host, port):
        self.connected = True

    def send(self, message):
        self.sent.append(message)

    def close(self):
        self.connected = False


def make_controller(mode="join"):
    controller = ClientController(connection_factory=FakeConnection)
    controller.connect(
        "127.0.0.1",
        8765,
        "Alice",
        mode,
        table_id="ABCD" if mode == "join" else "",
        buy_in=500,
    )
    return controller, FakeConnection.instances[-1]


def test_controller_answers_existing_join_protocol_prompts():
    controller, connection = make_controller()
    connection.on_message({"type": "request_lobby_action"})
    connection.on_message({"type": "request_table_id"})
    connection.on_message({"type": "request_name"})
    connection.on_message({"type": "request_buy_in"})

    assert connection.sent == [
        {"type": "lobby_action", "action": "join"},
        {"type": "table_id", "table_id": "ABCD"},
        {"type": "join", "name": "Alice"},
        {"type": "buy_in", "amount": controller.buy_in},
    ]


def test_controller_exposes_state_and_action_events_without_qt():
    controller, connection = make_controller()
    events = []
    controller.subscribe("*", lambda event, payload: events.append((event, payload)))
    state_message = {
        "type": "state",
        "state": {"pot": "12", "players": {}},
        "table": {"table_id": "ABCD", "seats": []},
    }
    action_message = {
        "type": "request_action",
        "legal_actions": ["fold", "call"],
        "to_call": "2",
    }

    connection.on_message(state_message)
    connection.on_message(action_message)
    controller.submit_action("call")

    assert ("state", state_message) in events
    assert ("action_required", action_message) in events
    assert connection.sent[-1] == {
        "type": "action",
        "action": "call",
        "amount": 0,
    }
