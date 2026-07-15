from decimal import Decimal

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


def test_controller_exposes_standalone_table_snapshots():
    controller, connection = make_controller()
    events = []
    controller.subscribe("*", lambda event, payload: events.append((event, payload)))
    table = {"table_id": "ABCD", "seats": []}

    connection.on_message({"type": "table", "table": table})

    assert controller.latest_table == table
    assert ("table", table) in events


def test_controller_exposes_hand_history_and_cancel_leave():
    controller, connection = make_controller()
    events = []
    controller.subscribe("*", lambda event, payload: events.append((event, payload)))

    connection.on_message(
        {
            "type": "hand_history",
            "history": ["New hand started.", "Alice bets 5."],
        }
    )
    connection.on_message(
        {
            "type": "leave_cancelled",
            "message": "Leave cancelled. You will stay at the table.",
        }
    )
    controller.cancel_leave()

    assert (
        "hand_history",
        ["New hand started.", "Alice bets 5."],
    ) in events
    assert (
        "leave_cancelled",
        "Leave cancelled. You will stay at the table.",
    ) in events
    assert connection.sent[-1] == {"type": "cancel_leave"}


def test_controller_exposes_allocator_lock_and_submits_updates():
    controller, connection = make_controller()
    events = []
    controller.subscribe("*", lambda event, payload: events.append((event, payload)))

    controller.submit_allocator_allocation([1, 2], [3, 4], [5, 6])
    controller.submit_allocator_allocation([2, 3], [1, 4], [5, 6])
    connection.on_message({"type": "allocator_locked"})

    assert connection.sent[-2:] == [
        {
            "type": "allocator_allocation",
            "top": [1, 2],
            "bottom": [3, 4],
            "hand": [5, 6],
            "ready": True,
        },
        {
            "type": "allocator_allocation",
            "top": [2, 3],
            "bottom": [1, 4],
            "hand": [5, 6],
            "ready": True,
        },
    ]
    assert ("allocator_locked", {"type": "allocator_locked"}) in events


def test_controller_auto_continues_for_legacy_servers():
    _, connection = make_controller()

    connection.on_message({"type": "request_continue"})

    assert connection.sent[-1] == {
        "type": "continue",
        "continue": True,
    }


def test_controller_submits_rebuy_or_leave():
    controller, connection = make_controller()

    controller.submit_rebuy("750.50")
    assert connection.sent[-1] == {
        "type": "rebuy",
        "rebuy": True,
        "amount": Decimal("750.50"),
    }

    controller.submit_rebuy()
    assert connection.sent[-1] == {
        "type": "rebuy",
        "rebuy": False,
    }


def test_controller_requests_an_orderly_table_leave():
    controller, connection = make_controller()

    controller.request_leave()

    assert connection.sent[-1] == {"type": "leave_table"}
