from decimal import Decimal

import pytest

from pof import PotOrFoldGame


@pytest.mark.parametrize("hole_cards", [4, 5, 6])
def test_pof_deals_configured_hole_cards_and_collects_antes(hole_cards):
    game = PotOrFoldGame(
        {"Alice": 100, "Bob": 100, "Cara": 100},
        ante=5,
        hole_cards=hole_cards,
        shuffle=False,
    )

    game.start_hand()

    assert all(len(player.hand) == hole_cards for player in game.players)
    assert all(player.stack == Decimal(95) for player in game.players)
    assert game.pot == Decimal(15)
    assert game.board == []


def test_pof_deals_flop_then_starts_action_on_small_blind():
    game = PotOrFoldGame(
        {"Alice": 100, "Bob": 100, "Cara": 100},
        ante=5,
        hole_cards=4,
        shuffle=False,
    )
    game.dealer_index = 0
    game.start_hand()

    game.deal_flop()

    assert len(game.board) == 3
    assert game.players[game.action_index].name == "Bob"
    assert game.legal_actions("Bob") == ["fold", "pot"]


def test_heads_up_pof_starts_action_on_dealer_small_blind():
    game = PotOrFoldGame(
        {"Alice": 100, "Bob": 100},
        ante=5,
        hole_cards=4,
        shuffle=False,
    )
    game.dealer_index = 0
    game.start_hand()

    game.deal_flop()

    assert game.players[game.action_index].name == "Alice"


def test_pof_opener_bets_current_pot_and_everyone_else_can_only_call_or_fold():
    game = PotOrFoldGame(
        {"Alice": 100, "Bob": 100, "Cara": 100},
        ante=5,
        hole_cards=4,
        shuffle=False,
    )
    game.start_hand()
    game.deal_flop()

    result = game.act("Bob", "pot")

    assert result.amount == Decimal(15)
    assert game.pot == Decimal(30)
    assert game.current_bet == Decimal(15)
    assert game.legal_actions("Cara") == ["fold", "call"]
    assert game.legal_actions("Alice") == ["fold", "call"]


def test_pof_passes_the_pot_or_fold_choice_on_when_first_player_folds():
    game = PotOrFoldGame(
        {"Alice": 100, "Bob": 100, "Cara": 100},
        ante=5,
        hole_cards=4,
        shuffle=False,
    )
    game.start_hand()
    game.deal_flop()

    game.act("Bob", "fold")

    assert game.players[game.action_index].name == "Cara"
    assert game.legal_actions("Cara") == ["fold", "pot"]


def test_pof_rejects_raises_and_run_twice_is_not_an_engine_action():
    game = PotOrFoldGame(
        {"Alice": 100, "Bob": 100},
        ante=5,
        hole_cards=4,
        shuffle=False,
    )
    game.start_hand()
    game.deal_flop()

    with pytest.raises(ValueError, match="pot or fold"):
        game.act("Alice", "raise", 20)


@pytest.mark.parametrize("hole_cards", [3, 7])
def test_pof_rejects_unsupported_hole_card_counts(hole_cards):
    with pytest.raises(ValueError, match="4, 5, 6"):
        PotOrFoldGame(
            {"Alice": 100, "Bob": 100},
            ante=5,
            hole_cards=hole_cards,
        )
