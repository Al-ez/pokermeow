from decimal import Decimal

from card import Card
from pineapple import PineappleGame


def c(rank, suit):
    return Card(rank, suit)


def make_game():
    return PineappleGame(
        {"Alice": 100, "Bob": 100, "Cara": 100},
        ante=5,
        shuffle=False,
    )


def test_pineapple_posts_antes_deals_three_cards_and_two_flops():
    game = make_game()

    game.start_hand()
    game.deal_flop()

    assert game.pot == Decimal(15)
    assert all(player.total_committed == Decimal(5) for player in game.players)
    assert all(len(player.hand) == 3 for player in game.players)
    assert len(game.top_board) == 3
    assert len(game.bottom_board) == 3
    assert game.min_raise == Decimal(5)


def test_pineapple_requires_discard_then_uses_standard_nlh_actions():
    game = make_game()
    game.start_hand()
    game.deal_flop()

    assert game.legal_actions("Bob") == []
    discarded = game.discard("Bob", 1)

    assert discarded not in game._player_by_name("Bob").hand
    assert len(game._player_by_name("Bob").hand) == 2
    assert game.legal_actions("Bob") == ["fold", "check", "bet", "all_in"]


def test_pineapple_deals_both_turns_and_rivers():
    game = make_game()
    game.start_hand()
    game.deal_flop()

    game.deal_turn()
    game.deal_river()

    assert len(game.top_board) == 5
    assert len(game.bottom_board) == 5
    assert game.board == game.top_board


def test_pineapple_showdown_splits_pot_across_both_holdem_boards():
    game = PineappleGame(
        {"Alice": 100, "Bob": 100},
        ante=5,
        shuffle=False,
    )
    alice, bob = game.players
    alice.hand = [c("A", "spades"), c("A", "hearts")]
    bob.hand = [c("K", "spades"), c("K", "hearts")]
    for player in game.players:
        player.stack = Decimal(0)
        player.total_committed = Decimal(100)
    game.pot = Decimal(200)
    game.hand_active = True
    game.top_board = [
        c("2", "clubs"),
        c("3", "diamonds"),
        c("4", "hearts"),
        c("8", "spades"),
        c("9", "clubs"),
    ]
    game.bottom_board = [
        c("K", "clubs"),
        c("3", "clubs"),
        c("4", "diamonds"),
        c("8", "hearts"),
        c("9", "diamonds"),
    ]
    game.board = list(game.top_board)

    result = game.showdown()

    assert result.amount_won == {
        "Alice": Decimal(100),
        "Bob": Decimal(100),
    }
    assert alice.stack == Decimal(100)
    assert bob.stack == Decimal(100)
