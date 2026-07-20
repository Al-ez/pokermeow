from helicopter import HelicopterGame


def test_turn_and_river_draw_three_cards_for_each_active_player():
    game = HelicopterGame({"Alice": 1000, "Bob": 1000}, shuffle=False)
    game.start_hand()
    game.deal_flop()

    game.deal_turn()
    assert [len(player.hand) for player in game.players] == [9, 9]

    game.deal_river()
    assert [len(player.hand) for player in game.players] == [12, 12]


def test_draw_is_equal_and_reduced_when_the_deck_is_short():
    game = HelicopterGame({"Alice": 1000, "Bob": 1000, "Cara": 1000}, shuffle=False)
    game.start_hand()
    game.deck.cards = game.deck.cards[:8]

    assert game._deal_equal_private_draw() == 2
    assert [len(player.hand) for player in game.players] == [8, 8, 8]
    assert game.deck.remaining() == 2


def test_twelve_available_cards_deal_two_each_to_five_players():
    game = HelicopterGame(
        {name: 1000 for name in ["A", "B", "C", "D", "E"]},
        shuffle=False,
    )
    game.start_hand()
    game.deck.cards = game.deck.cards[:12]

    assert game._deal_equal_private_draw() == 2
    assert [len(player.hand) for player in game.players] == [8, 8, 8, 8, 8]
    assert game.deck.remaining() == 2


def test_folded_private_cards_return_to_deck_and_folded_player_does_not_draw():
    game = HelicopterGame({"Alice": 1000, "Bob": 1000}, shuffle=False)
    game.start_hand()
    folded_cards = list(game.players[0].hand)
    before = game.deck.remaining()

    game.act("Alice", "fold")

    assert game.players[0].hand == []
    assert game.deck.remaining() == before + 6
    assert set(folded_cards).issubset(set(game.deck.cards))
    game._deal_equal_private_draw()
    assert len(game.players[0].hand) == 0
    assert len(game.players[1].hand) == 9


def test_allocation_selects_six_distinct_cards_from_a_larger_hand():
    game = HelicopterGame({"Alice": 1000, "Bob": 1000}, shuffle=False)
    game.start_hand()
    game.players[0].hand.extend([game.deck.deal_one() for _ in range(3)])
    cards = game.players[0].hand

    game.set_allocation("Alice", cards[0:2], cards[2:4], cards[6:8])

    assert game.allocations["Alice"].hand == cards[6:8]


def test_turn_draw_reserves_enough_cards_to_complete_both_river_boards():
    game = HelicopterGame(
        {name: 1000 for name in ["A", "B", "C", "D", "E", "F"]},
        shuffle=False,
    )
    game.start_hand()
    game.deal_flop()
    game.deal_turn()
    game.deal_river()

    assert len(game.top_board) == 5
    assert len(game.bottom_board) == 5


if __name__ == "__main__":
    test_turn_and_river_draw_three_cards_for_each_active_player()
    test_draw_is_equal_and_reduced_when_the_deck_is_short()
    test_twelve_available_cards_deal_two_each_to_five_players()
    test_folded_private_cards_return_to_deck_and_folded_player_does_not_draw()
    test_allocation_selects_six_distinct_cards_from_a_larger_hand()
    test_turn_draw_reserves_enough_cards_to_complete_both_river_boards()
    print("Helicopter variant tests passed.")
