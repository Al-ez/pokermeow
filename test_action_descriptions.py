from decimal import Decimal
import threading
from types import SimpleNamespace
from unittest.mock import patch

from server import PokerTableSession, Seat, Table


def action_result(action, amount, current_bet):
    return SimpleNamespace(
        player="Bob",
        action=action,
        amount=Decimal(amount),
        current_bet=Decimal(current_bet),
    )


def test_raise_description_uses_raise_increment_not_total_commitment():
    result = action_result("raise", "15", "15")

    description = PokerTableSession._describe_action(
        result,
        previous_current_bet=Decimal("5"),
    )

    assert description == "Bob raises 10 to 15."


def test_raise_description_handles_existing_blind_commitment():
    result = action_result("raise", "13", "15")

    description = PokerTableSession._describe_action(
        result,
        previous_current_bet=Decimal("5"),
    )

    assert description == "Bob raises 10 to 15."


def test_net_winnings_exclude_the_winners_own_contribution():
    session = object.__new__(PokerTableSession)
    session.game = SimpleNamespace(
        players=[
            SimpleNamespace(
                name="Alice",
                total_committed=Decimal("1001"),
            ),
            SimpleNamespace(
                name="Bob",
                total_committed=Decimal("2"),
            ),
        ]
    )

    net = session._net_winnings({"Alice": Decimal("1003")})

    assert net == {"Alice": Decimal("2")}


def test_busted_seat_is_held_until_rebuy_decision():
    client = SimpleNamespace(name="Alice", send=lambda message: None)
    table = Table(max_seats=2)
    table.seats[0] = Seat(client=client, stack=Decimal("100"))
    game = SimpleNamespace(
        players=[SimpleNamespace(name="Alice", stack=Decimal("0"))]
    )

    busted = table.update_stacks(game)

    assert busted == [client]
    assert table.seats[0].client is client
    assert table.seats[0].stack == Decimal("0")
    assert table.seats[0].reserved is True
    assert table.set_stack(client, Decimal("500")) is True
    assert table.seats[0].stack == Decimal("500")
    table.activate_reserved_seats()
    assert table.seats[0].reserved is False


def test_valid_rebuy_restores_the_stack_and_keeps_the_seat():
    sent = []
    socket_marker = object()
    client = SimpleNamespace(
        name="Alice",
        buy_in=Decimal("100"),
        socket=socket_marker,
        send=sent.append,
        recv=lambda: {
            "type": "rebuy",
            "rebuy": True,
            "amount": "500",
        },
    )
    restored = {}
    removed = []
    session = object.__new__(PokerTableSession)
    session.table = SimpleNamespace(
        set_stack=lambda selected, amount: (
            restored.update(client=selected, amount=amount) or True
        ),
        remove_client=removed.append,
    )

    with patch(
        "server.select.select",
        return_value=([socket_marker], [], []),
    ):
        session._handle_rebuy(client)

    assert restored == {
        "client": client,
        "amount": Decimal("500"),
    }
    assert removed == []
    assert client.buy_in == Decimal("500")
    assert sent[-1]["type"] == "rebought"


def test_rebuy_offer_does_not_block_the_table_loop():
    started = threading.Event()
    release = threading.Event()
    session = object.__new__(PokerTableSession)
    session._handle_rebuy = lambda client: (
        started.set(),
        release.wait(1),
    )

    session._offer_rebuys([SimpleNamespace(name="Alice")])

    assert started.wait(0.2)
    release.set()


def test_pending_rebuy_is_not_prompted_again_after_another_hand():
    pending_client = SimpleNamespace(name="Alice")
    table = Table(max_seats=2)
    table.seats[0] = Seat(
        client=pending_client,
        stack=Decimal("0"),
        reserved=True,
    )
    another_hand = SimpleNamespace(
        players=[SimpleNamespace(name="Bob", stack=Decimal("100"))]
    )

    busted = table.update_stacks(another_hand)

    assert busted == []
    assert table.seats[0].reserved is True


def test_active_player_leave_is_deferred_until_hand_ends():
    sent = []
    client = SimpleNamespace(
        name="Alice",
        leave_after_hand=False,
        connected=True,
        send=sent.append,
    )
    table = Table(max_seats=2)
    table.seats[0] = Seat(client=client, stack=Decimal("100"))
    table.hand_in_progress = True
    session = object.__new__(PokerTableSession)
    session.table = table
    session.game = SimpleNamespace(
        players=[SimpleNamespace(name="Alice", folded=False)]
    )

    session._handle_leave_request(client)

    assert client.leave_after_hand is True
    assert table.seats[0] is not None
    assert sent[-1]["type"] == "leave_scheduled"

    removed = session._remove_scheduled_leavers()
    assert removed == [client]
    assert table.seats[0] is None
    assert sent[-1]["type"] == "left_table"


def test_folded_player_can_leave_immediately():
    sent = []
    client = SimpleNamespace(
        name="Alice",
        leave_after_hand=False,
        connected=True,
        send=sent.append,
    )
    table = Table(max_seats=2)
    table.seats[0] = Seat(client=client, stack=Decimal("100"))
    table.hand_in_progress = True
    session = object.__new__(PokerTableSession)
    session.table = table
    session.game = SimpleNamespace(
        players=[SimpleNamespace(name="Alice", folded=True)]
    )

    session._handle_leave_request(client)

    assert client.leave_after_hand is False
    assert table.seats[0] is None
    assert sent[-1]["type"] == "left_table"
