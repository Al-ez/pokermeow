from fractions import Fraction
from decimal import Decimal

from allocator import Allocation, AllocatorGame, AllocatorScore
from card import Card
from plo import PotLimitOmahaGame


def c(rank, suit):
    return Card(rank, suit)


def make_game():
    return AllocatorGame({"Alice": 1000, "Bob": 1000}, shuffle=False)


def assert_raises(error_type, message_part, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except error_type as error:
        if message_part not in str(error):
            raise AssertionError(
                f"Expected error message to contain {message_part!r}, got {str(error)!r}"
            )
        return

    raise AssertionError(f"Expected {error_type.__name__} to be raised")


def test_allocation_validation_accepts_all_six_cards_once():
    game = make_game()
    cards = [
        c("A", "spades"),
        c("K", "spades"),
        c("Q", "hearts"),
        c("J", "hearts"),
        c("10", "clubs"),
        c("9", "clubs"),
    ]
    allocation = Allocation(
        top=cards[0:2],
        bottom=cards[2:4],
        hand=cards[4:6],
    )

    game.validate_allocation(cards, allocation)


def test_allocation_validation_rejects_duplicate_card_usage():
    game = make_game()
    cards = [
        c("A", "spades"),
        c("K", "spades"),
        c("Q", "hearts"),
        c("J", "hearts"),
        c("10", "clubs"),
        c("9", "clubs"),
    ]
    allocation = Allocation(
        top=[cards[0], cards[1]],
        bottom=[cards[0], cards[2]],
        hand=[cards[4], cards[5]],
    )

    assert_raises(ValueError, "same card", game.validate_allocation, cards, allocation)


def test_allocation_validation_rejects_missing_card():
    game = make_game()
    cards = [
        c("A", "spades"),
        c("K", "spades"),
        c("Q", "hearts"),
        c("J", "hearts"),
        c("10", "clubs"),
        c("9", "clubs"),
    ]
    outsider = c("8", "diamonds")
    allocation = Allocation(
        top=[cards[0], cards[1]],
        bottom=[cards[2], cards[3]],
        hand=[cards[4], outsider],
    )

    assert_raises(
        ValueError,
        "every private card",
        game.validate_allocation,
        cards,
        allocation,
    )


def test_hand_strength_pairs_beat_non_pairs_and_rank_by_pair():
    assert AllocatorGame.hand_strength_rank([c("A", "spades"), c("A", "hearts")]) > (
        AllocatorGame.hand_strength_rank([c("K", "spades"), c("K", "hearts")])
    )
    assert AllocatorGame.hand_strength_rank([c("2", "spades"), c("2", "hearts")]) > (
        AllocatorGame.hand_strength_rank([c("A", "spades"), c("K", "hearts")])
    )


def test_hand_strength_non_pairs_ignore_suits_and_tie():
    suited_ak = AllocatorGame.hand_strength_rank([c("A", "spades"), c("K", "spades")])
    offsuit_ak = AllocatorGame.hand_strength_rank([c("K", "clubs"), c("A", "diamonds")])

    assert suited_ak == offsuit_ak


def test_board_tie_splits_one_point_when_board_plays():
    game = make_game()
    alice_cards = [
        c("2", "clubs"),
        c("3", "diamonds"),
        c("4", "clubs"),
        c("5", "diamonds"),
        c("A", "clubs"),
        c("K", "diamonds"),
    ]
    bob_cards = [
        c("6", "clubs"),
        c("7", "diamonds"),
        c("8", "clubs"),
        c("9", "diamonds"),
        c("A", "diamonds"),
        c("K", "clubs"),
    ]

    game.players[0].hand = alice_cards
    game.players[1].hand = bob_cards
    game.top_board = [
        c("A", "hearts"),
        c("K", "hearts"),
        c("Q", "hearts"),
        c("J", "hearts"),
        c("10", "hearts"),
    ]
    game.bottom_board = [
        c("2", "spades"),
        c("4", "spades"),
        c("6", "spades"),
        c("8", "spades"),
        c("10", "spades"),
    ]
    game.set_allocation("Alice", alice_cards[0:2], alice_cards[2:4], alice_cards[4:6])
    game.set_allocation("Bob", bob_cards[0:2], bob_cards[2:4], bob_cards[4:6])

    scores = game.calculate_scores()

    assert scores["Alice"].top_board_points == Fraction(1, 2)
    assert scores["Bob"].top_board_points == Fraction(1, 2)


def test_point_splitting_for_hand_strength_tie():
    game = make_game()
    alice_cards = [
        c("2", "clubs"),
        c("3", "diamonds"),
        c("4", "clubs"),
        c("5", "diamonds"),
        c("A", "clubs"),
        c("K", "diamonds"),
    ]
    bob_cards = [
        c("6", "clubs"),
        c("7", "diamonds"),
        c("8", "clubs"),
        c("9", "diamonds"),
        c("A", "diamonds"),
        c("K", "clubs"),
    ]
    game.players[0].hand = alice_cards
    game.players[1].hand = bob_cards
    game.set_allocation("Alice", alice_cards[0:2], alice_cards[2:4], alice_cards[4:6])
    game.set_allocation("Bob", bob_cards[0:2], bob_cards[2:4], bob_cards[4:6])

    points = game._score_hand_strength(game.players)

    assert points == {"Alice": Fraction(1, 2), "Bob": Fraction(1, 2)}


def test_allocator_score_details_are_engine_authoritative():
    game = make_game()
    alice_cards = [
        c("2", "clubs"), c("3", "diamonds"),
        c("4", "clubs"), c("5", "diamonds"),
        c("A", "clubs"), c("K", "diamonds"),
    ]
    bob_cards = [
        c("6", "clubs"), c("7", "diamonds"),
        c("8", "clubs"), c("9", "diamonds"),
        c("A", "diamonds"), c("K", "clubs"),
    ]
    board = [
        c("A", "hearts"), c("K", "hearts"),
        c("Q", "hearts"), c("J", "hearts"), c("10", "hearts"),
    ]
    game.players[0].hand = alice_cards
    game.players[1].hand = bob_cards
    game.set_allocation(
        "Alice", alice_cards[0:2], alice_cards[2:4], alice_cards[4:6]
    )
    game.set_allocation(
        "Bob", bob_cards[0:2], bob_cards[2:4], bob_cards[4:6]
    )

    board_details = game.board_score_details(game.players, "top", board)
    strength_details = game.hand_strength_score_details(game.players)

    assert board_details["winners"] == ["Alice", "Bob"]
    assert board_details["points"] == Fraction(1, 2)
    assert strength_details["winners"] == ["Alice", "Bob"]
    assert strength_details["points"] == Fraction(1, 2)


def test_pot_limit_variants_share_limit_behaviour():
    for game_class in (PotLimitOmahaGame, AllocatorGame):
        game = game_class({"Alice": 1000, "Bob": 1000}, shuffle=False)
        assert game.max_bet("Alice") == Decimal("10")
        assert "all_in" not in game.legal_actions("Alice")


def test_overall_winner_determined_by_total_allocator_score():
    alice = AllocatorScore(Fraction(1, 1), Fraction(0, 1), Fraction(1, 2))
    bob = AllocatorScore(Fraction(0, 1), Fraction(1, 1), Fraction(0, 1))

    assert alice.total > bob.total


def test_side_pot_winners_use_allocator_scores():
    game = AllocatorGame({"Alice": 100, "Bob": 50, "Cara": 100}, shuffle=False)
    alice, bob, cara = game.players

    alice.commit(100)
    bob.commit(50)
    cara.commit(100)
    game.pot = 250

    scores = {
        "Alice": AllocatorScore(Fraction(2, 1), Fraction(0, 1), Fraction(0, 1)),
        "Bob": AllocatorScore(Fraction(3, 1), Fraction(0, 1), Fraction(0, 1)),
        "Cara": AllocatorScore(Fraction(1, 1), Fraction(0, 1), Fraction(0, 1)),
    }
    amount_won = {}

    winners = game._award_showdown_pots(
        game.players,
        scores,
        amount_won,
        score_key=lambda score: (score.total,),
    )

    assert winners == ["Bob", "Alice"]
    assert amount_won == {"Bob": 150, "Alice": 100}


def test_allocator_side_pots_are_rescored_by_eligible_players():
    game = AllocatorGame({"Alice": 100, "Bob": 50, "Cara": 100}, shuffle=False)
    alice, bob, cara = game.players

    alice.commit(100)
    bob.commit(50)
    cara.commit(100)
    game.pot = 250

    def calculate_scores(active_players=None):
        names = {player.name for player in active_players}
        if names == {"Alice", "Bob", "Cara"}:
            return {
                "Alice": AllocatorScore(Fraction(2, 1), Fraction(0, 1), Fraction(0, 1)),
                "Bob": AllocatorScore(Fraction(3, 1), Fraction(0, 1), Fraction(0, 1)),
                "Cara": AllocatorScore(Fraction(1, 1), Fraction(0, 1), Fraction(0, 1)),
            }

        if names == {"Alice", "Cara"}:
            return {
                "Alice": AllocatorScore(Fraction(1, 1), Fraction(0, 1), Fraction(0, 1)),
                "Cara": AllocatorScore(Fraction(2, 1), Fraction(0, 1), Fraction(0, 1)),
            }

        raise AssertionError(f"Unexpected eligible players: {names}")

    game.calculate_scores = calculate_scores
    amount_won = {}

    winners = game._award_allocator_pots(game.players, amount_won)

    assert winners == ["Bob", "Cara"]
    assert amount_won == {"Bob": Decimal("150"), "Cara": Decimal("100")}
    assert game.pot_results[0]["eligible_players"] == ["Alice", "Bob", "Cara"]
    assert game.pot_results[1]["eligible_players"] == ["Alice", "Cara"]
    assert game.pot_results[1]["scores"]["Cara"].total == Fraction(2, 1)
    assert game.pot_results[1]["scores"]["Alice"].total == Fraction(1, 1)


def run_tests():
    tests = [
        test_allocation_validation_accepts_all_six_cards_once,
        test_allocation_validation_rejects_duplicate_card_usage,
        test_allocation_validation_rejects_missing_card,
        test_hand_strength_pairs_beat_non_pairs_and_rank_by_pair,
        test_hand_strength_non_pairs_ignore_suits_and_tie,
        test_board_tie_splits_one_point_when_board_plays,
        test_point_splitting_for_hand_strength_tie,
        test_allocator_score_details_are_engine_authoritative,
        test_pot_limit_variants_share_limit_behaviour,
        test_overall_winner_determined_by_total_allocator_score,
        test_side_pot_winners_use_allocator_scores,
        test_allocator_side_pots_are_rescored_by_eligible_players,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_tests()
