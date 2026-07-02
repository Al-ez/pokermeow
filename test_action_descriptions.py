from decimal import Decimal
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
    client = SimpleNamespace(name="Alice")
    table = Table(max_seats=2)
    table.seats[0] = Seat(client=client, stack=Decimal("100"))
    game = SimpleNamespace(
        players=[SimpleNamespace(name="Alice", stack=Decimal("0"))]
    )

    busted = table.update_stacks(game)

    assert busted == [client]
    assert table.seats[0].client is client
    assert table.seats[0].stack == Decimal("0")
    assert table.set_stack(client, Decimal("500")) is True
    assert table.seats[0].stack == Decimal("500")


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
