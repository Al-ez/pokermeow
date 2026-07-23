from decimal import Decimal

from card import Card
from nlh import NoLimitHoldemGame
from server import run_count_for_votes


def c(rank, suit):
    return Card(rank, suit)


def test_two_board_showdown_splits_the_pot_between_board_winners():
    game = NoLimitHoldemGame({"Alice": 100, "Bob": 100}, shuffle=False)
    alice, bob = game.players
    alice.hand = [c("A", "spades"), c("A", "hearts")]
    bob.hand = [c("K", "spades"), c("K", "hearts")]
    for player in game.players:
        player.stack = Decimal(0)
        player.total_committed = Decimal(100)
        player.all_in = True
    game.pot = Decimal(200)
    game.board = [
        c("2", "clubs"),
        c("3", "diamonds"),
        c("4", "hearts"),
        c("8", "spades"),
        c("9", "clubs"),
    ]
    second_board = [
        c("K", "clubs"),
        c("3", "clubs"),
        c("4", "diamonds"),
        c("8", "hearts"),
        c("9", "diamonds"),
    ]

    result = game.showdown_boards([game.board, second_board])

    assert result.amount_won == {
        "Alice": Decimal(100),
        "Bob": Decimal(100),
    }
    assert alice.stack == Decimal(100)
    assert bob.stack == Decimal(100)


def test_one_board_showdown_boards_matches_normal_full_pot_award():
    game = NoLimitHoldemGame({"Alice": 100, "Bob": 100}, shuffle=False)
    alice, bob = game.players
    alice.hand = [c("A", "spades"), c("A", "hearts")]
    bob.hand = [c("K", "spades"), c("K", "hearts")]
    for player in game.players:
        player.stack = Decimal(0)
        player.total_committed = Decimal(100)
    game.pot = Decimal(200)
    board = [
        c("2", "clubs"),
        c("3", "diamonds"),
        c("4", "hearts"),
        c("8", "spades"),
        c("9", "clubs"),
    ]

    result = game.showdown_boards([board])

    assert result.amount_won == {"Alice": Decimal(200)}


def test_run_it_twice_requires_every_active_player_to_choose_twice():
    players = {"Alice", "Bob", "Cara"}

    assert run_count_for_votes(
        players,
        {"Alice": "twice", "Bob": "twice", "Cara": "twice"},
    ) == 2
    assert run_count_for_votes(
        players,
        {"Alice": "twice", "Bob": "once", "Cara": "twice"},
    ) == 1
    assert run_count_for_votes(
        players,
        {"Alice": "twice", "Bob": "twice"},
    ) == 1
