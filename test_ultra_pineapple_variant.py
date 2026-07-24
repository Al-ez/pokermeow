from decimal import Decimal

from ultra_pineapple import UltraPineappleGame


def make_game():
    return UltraPineappleGame(
        {"Alice": 100, "Bob": 100},
        ante=5,
        shuffle=False,
    )


def test_ultra_pineapple_deals_five_cards_and_discards_on_every_street():
    game = make_game()
    game.start_hand()

    assert all(len(player.hand) == 5 for player in game.players)
    assert game.pot == Decimal(10)

    game.deal_flop()
    assert game.legal_actions("Alice") == []
    game.discard("Alice", 0)
    assert len(game._player_by_name("Alice").hand) == 4
    assert "check" in game.legal_actions("Alice")

    game.deal_turn()
    assert game.legal_actions("Alice") == []
    game.discard("Alice", 0)
    assert len(game._player_by_name("Alice").hand) == 3
    assert "check" in game.legal_actions("Alice")

    game.deal_river()
    assert game.legal_actions("Alice") == []
    game.discard("Alice", 0)
    assert len(game._player_by_name("Alice").hand) == 2
    assert "check" in game.legal_actions("Alice")


def test_ultra_pineapple_rejects_a_second_discard_on_the_same_street():
    game = make_game()
    game.start_hand()
    game.deal_flop()
    game.discard("Alice", 0)

    try:
        game.discard("Alice", 0)
    except ValueError as error:
        assert "already discarded" in str(error)
    else:
        raise AssertionError("A second flop discard should be rejected")
