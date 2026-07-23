from decimal import Decimal

from aof import AOFGame
from game_categories import BoardCategory


def make_game():
    return AOFGame(
        {"Alice": 100, "Bob": 100},
        ante=3,
        multiplier=10,
        shuffle=False,
    )


def test_aof_posts_antes_and_deals_three_cards_without_a_flop():
    game = make_game()
    game.start_hand()

    assert game.pot == Decimal(6)
    assert game.board == []
    assert all(len(player.hand) == 3 for player in game.players)
    assert all(player.total_committed == Decimal(3) for player in game.players)


def test_aof_requires_discard_before_action():
    game = make_game()
    game.start_hand()

    assert game.legal_actions("Alice") == []
    try:
        game.act("Alice", "all_in")
    except ValueError as error:
        assert "discard" in str(error).lower()
    else:
        raise AssertionError("AOF action should require a discard")


def test_aof_discard_leaves_two_cards_and_unlocks_fixed_decisions():
    game = make_game()
    game.start_hand()
    discarded = game.discard("Alice", 1)

    assert discarded not in game._player_by_name("Alice").hand
    assert len(game._player_by_name("Alice").hand) == 2
    assert game.legal_actions("Alice") == ["fold", "all_in"]


def test_aof_fixed_all_in_commits_ante_times_multiplier_less_ante():
    game = make_game()
    game.start_hand()
    game.discard("Alice", 0)

    assert game.fixed_all_in_amount("Alice") == Decimal(27)
    result = game.act("Alice", "all_in")

    alice = game._player_by_name("Alice")
    assert result.amount == Decimal(27)
    assert alice.total_committed == Decimal(30)
    assert alice.stack == Decimal(70)
    assert alice.all_in


def test_aof_is_a_single_board_game_and_multiplier_has_minimum():
    assert AOFGame.board_category is BoardCategory.SINGLE_BOARD
    try:
        AOFGame({"Alice": 100, "Bob": 100}, ante=3, multiplier=9)
    except ValueError as error:
        assert "at least 10" in str(error)
    else:
        raise AssertionError("Multiplier below 10 should be rejected")
