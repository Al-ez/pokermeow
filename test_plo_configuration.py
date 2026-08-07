from card import Card
from game_categories import BoardCategory
from plo import PotLimitOmahaGame


def test_plo_deals_configured_number_of_hole_cards():
    for count in (4, 5, 6):
        game = PotLimitOmahaGame(
            {"Alice": 100, "Bob": 100},
            hole_cards=count,
            boards=1,
            shuffle=False,
        )
        game.start_hand()
        assert all(len(player.hand) == count for player in game.players)


def test_two_board_plo_deals_two_complete_boards():
    game = PotLimitOmahaGame(
        {"Alice": 100, "Bob": 100},
        hole_cards=5,
        boards=2,
        shuffle=False,
    )
    game.start_hand()
    game.deal_flop()
    game.deal_turn()
    game.deal_river()

    assert game.board_category is BoardCategory.DOUBLE_BOARD
    assert len(game.top_board) == 5
    assert len(game.bottom_board) == 5
    assert game.board == game.top_board


def test_six_card_plo_still_uses_exactly_two_hole_cards():
    game = PotLimitOmahaGame(
        {"Alice": 100, "Bob": 100},
        hole_cards=6,
        boards=1,
        shuffle=False,
    )
    royal_in_hole_cards = [
        Card("A", "hearts"),
        Card("K", "hearts"),
        Card("Q", "hearts"),
        Card("J", "hearts"),
        Card("10", "hearts"),
        Card("2", "clubs"),
    ]
    board = [
        Card("3", "clubs"),
        Card("5", "diamonds"),
        Card("7", "spades"),
        Card("8", "clubs"),
        Card("9", "diamonds"),
    ]

    score = game._best_plo_hand(royal_in_hole_cards, board)

    assert score[3] != "straight flush"
    assert sum(card in royal_in_hole_cards for card in score[2]) == 2


def test_bomb_pot_mode_posts_configured_bb_ante_without_preflop_bets():
    game = PotLimitOmahaGame(
        {"Alice": 100, "Bob": 100, "Carol": 100},
        big_blind=2,
        mode="bomb_pot",
        ante_bb=3,
        shuffle=False,
    )

    game.start_hand()

    assert game.pot == 18
    assert game.current_bet == 0
    assert all(player.current_bet == 6 for player in game.players)
    assert all(player.total_committed == 6 for player in game.players)
