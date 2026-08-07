from card import Card
from network_protocol import visible_state_for
from terminator import TerminatorGame
import pytest


def card(rank, suit="spades"):
    return Card(rank, suit)


def make_game():
    return TerminatorGame({"Alice": 100, "Bob": 100}, ante=5, shuffle=False)


def test_terminator_posts_ante_and_deals_six_cards():
    game = make_game()
    game.start_hand()

    assert game.pot == 10
    assert all(len(player.hand) == 6 for player in game.players)


def test_chosen_flop_ranks_destroy_every_hand_and_the_live_board():
    game = make_game()
    game.start_hand()
    game.top_board = [card("A"), card("J", "hearts"), card("9", "clubs")]
    game.bottom_board = [card("A", "diamonds"), card("7"), card("2")]
    game.players[0].hand = [card("A"), card("K"), card("J"), card("4")]
    game.players[1].hand = [card("9"), card("Q"), card("3")]

    game.choose_terminated_board("top")

    assert game.terminated_ranks == {"A", "J", "9"}
    assert [item.rank for item in game.players[0].hand] == ["K", "4"]
    assert [item.rank for item in game.players[1].hand] == ["Q", "3"]
    assert [item.rank for item in game.bottom_board] == ["7", "2"]
    assert game.board == game.bottom_board


def test_later_terminator_card_decimates_rank_and_live_collateral():
    game = make_game()
    game.start_hand()
    game.top_board = [card("A"), card("J"), card("9")]
    game.bottom_board = [card("7"), card("2"), card("K")]
    game.street = 3
    game.choose_terminated_board("top")
    game.players[0].hand = [card("7"), card("Q")]
    game.deck.cards = [card("4"), card("7"), card("3")]

    game.deal_turn()

    assert "7" in game.terminated_ranks
    assert [item.rank for item in game.players[0].hand] == ["Q"]
    assert "7" not in [item.rank for item in game.live_board]


def test_short_surviving_hands_use_available_cards_only():
    game = make_game()
    trip_twos = game._score_hand(
        [card("2", "hearts"), card("2", "clubs")],
        [card("2", "diamonds")],
    )
    aces = game._score_hand([card("A"), card("A", "hearts")], [card("2")])
    kings = game._score_hand([card("K"), card("K", "hearts")], [card("2")])

    assert trip_twos[:2] > aces[:2] > kings[:2]
    assert trip_twos[3] == "three of a kind"


def test_dealer_hole_cards_stay_hidden_until_a_board_is_chosen():
    game = make_game()
    game.start_hand()
    game.deal_flop()
    dealer = game.players[game.dealer_index].name

    hidden = visible_state_for(game, dealer)
    assert "hand" not in hidden["players"][dealer]

    game.choose_terminated_board("top")
    revealed = visible_state_for(game, dealer)
    assert "hand" in revealed["players"][dealer]


def test_terminator_betting_is_capped_at_the_size_of_the_pot():
    game = make_game()
    game.start_hand()
    player = game.players[game.action_index]

    assert game.max_bet(player.name) == 10
    assert "all_in" not in game.legal_actions(player.name)
    with pytest.raises(ValueError, match="Pot-limit bet"):
        game.act(player.name, "bet", 11)

    result = game.act(player.name, "bet", 10)
    assert result.amount == 10
