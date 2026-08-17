from decimal import Decimal

from card import Card
from esg import ESGGame
from game_categories import BoardCategory
from network_protocol import visible_state_for


def c(rank, suit):
    return Card(rank, suit)


def test_esg_starts_six_cards_with_blinds_and_preflop_action():
    game = ESGGame({"Alice": 100, "Bob": 100, "Cara": 100}, shuffle=False)
    game.start_hand()

    assert [len(player.hand) for player in game.players] == [6, 6, 6]
    assert game.pot == Decimal("3")
    assert game.current_bet == Decimal("2")
    assert game.players[game.action_index].name == "Alice"
    assert game.board_category is BoardCategory.DOUBLE_BOARD


def test_esg_draws_equally_while_reserving_future_board_cards():
    game = ESGGame(
        {name: 100 for name in ("A", "B", "C", "D", "E")},
        shuffle=False,
    )
    game.start_hand()
    game.deal_flop()
    assert [len(player.hand) for player in game.players] == [7] * 5

    game.deal_turn()
    assert [len(player.hand) for player in game.players] == [7] * 5

    game.deal_river()
    assert [len(player.hand) for player in game.players] == [7] * 5
    assert len(game.top_board) == len(game.bottom_board) == 5


def test_esg_deals_zero_when_no_equal_draw_is_available():
    game = ESGGame(
        {name: 100 for name in ("A", "B", "C", "D", "E", "F", "G")},
        shuffle=False,
    )
    game.start_hand()
    game.deal_flop()
    assert [len(player.hand) for player in game.players] == [6] * 7


def test_esg_deck_size_is_public_and_folded_cards_return_to_it():
    game = ESGGame({"Alice": 100, "Bob": 100, "Cara": 100}, shuffle=False)
    game.start_hand()
    assert visible_state_for(game, "Bob")["deck_size"] == 34

    game.act("Alice", "fold")
    assert visible_state_for(game, "Bob")["deck_size"] == 40


def test_esg_scores_plo_boards_and_best_private_five_without_allocation():
    game = ESGGame({"Alice": 100, "Bob": 100}, shuffle=False)
    game.start_hand()
    game.top_board = [
        c("A", "spades"), c("K", "spades"), c("Q", "spades"),
        c("2", "clubs"), c("3", "diamonds"),
    ]
    game.bottom_board = [
        c("9", "clubs"), c("9", "diamonds"), c("4", "hearts"),
        c("5", "spades"), c("6", "clubs"),
    ]
    game.board = list(game.top_board)
    game.players[0].hand = [
        c("J", "spades"), c("10", "spades"),
        c("8", "hearts"), c("8", "diamonds"),
        c("8", "clubs"), c("8", "spades"),
    ]
    game.players[1].hand = [
        c("A", "hearts"), c("A", "diamonds"),
        c("K", "hearts"), c("K", "diamonds"),
        c("7", "clubs"), c("2", "hearts"),
    ]

    scores = game.calculate_scores()
    assert scores["Alice"].top_board_points == 1
    assert scores["Alice"].hand_strength_points == 1
    assert game.hand_strength_score_details(game.players)["players"]["Alice"]["label"] == "four of a kind"


def test_esg_side_pots_are_rescored_for_eligible_players():
    game = ESGGame({"Alice": 100, "Bob": 50, "Cara": 100}, shuffle=False)
    game.start_hand()
    for player, committed in zip(game.players, (100, 50, 100)):
        player.total_committed = Decimal(committed)
    game.calculate_scores = lambda players=None: {
        player.name: type("Score", (), {"total": Decimal(
            {"Alice": 2, "Bob": 3, "Cara": 1}[player.name]
            if len(players or game.players) == 3
            else {"Alice": 1, "Cara": 2}[player.name]
        )})()
        for player in (players or game.players)
    }
    amount_won = {}
    winners = game._award_allocator_pots(game.players, amount_won)
    assert winners == ["Bob", "Cara"]
    assert amount_won == {"Bob": Decimal("150"), "Cara": Decimal("100")}
