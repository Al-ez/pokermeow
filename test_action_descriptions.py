from decimal import Decimal
from types import SimpleNamespace

from server import PokerTableSession


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
