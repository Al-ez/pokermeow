from decimal import Decimal

from nlh import NoLimitHoldemGame


def make_started_game():
    game = NoLimitHoldemGame(
        {"Alice": 100, "Bob": 100},
        small_blind=1,
        big_blind=2,
        shuffle=False,
    )
    game.start_hand()
    return game


def test_call_amount_is_capped_by_the_players_remaining_stack():
    game = make_started_game()
    alice = game._player_by_name("Alice")
    alice.stack = Decimal(7)
    alice.current_bet = Decimal(3)
    game.current_bet = Decimal(20)

    assert game.amount_to_call("Alice") == Decimal(7)


def test_call_amount_remains_the_outstanding_bet_when_stack_is_sufficient():
    game = make_started_game()
    alice = game._player_by_name("Alice")
    alice.stack = Decimal(50)
    alice.current_bet = Decimal(3)
    game.current_bet = Decimal(20)

    assert game.amount_to_call("Alice") == Decimal(17)


def test_short_stack_call_commits_the_same_amount_that_is_advertised():
    game = make_started_game()
    alice = game._player_by_name("Alice")
    alice.stack = Decimal(7)
    alice.current_bet = Decimal(3)
    game.current_bet = Decimal(20)
    advertised_call = game.amount_to_call("Alice")

    result = game.act("Alice", "call")

    assert result.amount == advertised_call == Decimal(7)
    assert alice.stack == Decimal(0)
    assert alice.all_in
