from typing import Dict, List

from allocator import AllocatorGame
from card import Card
from deck import Deck
from nlh import HandEvaluator, ZERO
from plo import PotLimitOmahaGame


class ESGGame(AllocatorGame):
    """Extremely Stupid Game: pot-limit, double-board, equal street draws."""

    MAX_STREET_DRAW = 3
    requires_allocator_allocation = False
    has_preflop_action = True

    def __init__(
        self,
        player_stacks: Dict[str, int],
        small_blind=1,
        big_blind=2,
        shuffle=True,
    ):
        super().__init__(
            player_stacks,
            small_blind=small_blind,
            big_blind=big_blind,
            shuffle=shuffle,
            bomb_pot_ante=0,
        )

    def start_hand(self) -> None:
        self.deck = Deck(shuffle=self.shuffle)
        self.board = []
        self.top_board = []
        self.bottom_board = []
        self.allocations = {}
        self.pot_results = []
        self.pot = ZERO
        self.current_bet = ZERO
        self.min_raise = self.big_blind
        self.hand_active = True

        for player in self.players:
            player.reset_for_hand()

        self._deal_hole_cards()
        self._post_blinds()
        if len(self.players) == 2:
            self.action_index = self.dealer_index
        else:
            self.action_index = self._next_active_index(self._big_blind_index())

    def act(self, player_name: str, action: str, amount=0):
        result = super().act(player_name, action, amount)
        if result.action == "fold":
            player = self._player_by_name(player_name)
            self.deck.cards.extend(player.hand)
            player.hand.clear()
            if self.shuffle:
                self.deck.shuffle()
        return result

    def deal_flop(self):
        cards = super().deal_flop()
        self._deal_equal_private_draw(reserve=6)
        return cards

    def deal_turn(self):
        cards = super().deal_turn()
        self._deal_equal_private_draw(reserve=3)
        return cards

    def deal_river(self):
        cards = super().deal_river()
        self._deal_equal_private_draw()
        return cards

    def _deal_equal_private_draw(self, reserve=0) -> int:
        players = self.active_players()
        if not players:
            return 0
        available = max(0, self.deck.remaining() - reserve)
        cards_each = min(self.MAX_STREET_DRAW, available // len(players))
        for _ in range(cards_each):
            for player in players:
                player.receive_card(self.deck.deal_one())
        return cards_each

    def calculate_scores(self, active_players=None):
        if active_players is None:
            active_players = [player for player in self.players if not player.folded]
        if len(self.top_board) != 5 or len(self.bottom_board) != 5:
            raise RuntimeError("ESG scoring requires complete top and bottom boards")

        top_points = self._score_board(active_players, "top", self.top_board)
        bottom_points = self._score_board(active_players, "bottom", self.bottom_board)
        hand_points = self._score_hand_strength(active_players)
        return {
            player.name: self._score_type(
                top_points.get(player.name, 0),
                bottom_points.get(player.name, 0),
                hand_points.get(player.name, 0),
            )
            for player in active_players
        }

    @staticmethod
    def _score_type(top, bottom, hand):
        from allocator import AllocatorScore
        return AllocatorScore(top, bottom, hand)

    def board_score_details(self, active_players, allocation_name, board):
        player_results = {}
        for player in active_players:
            score = PotLimitOmahaGame._best_plo_hand_from_available(
                player.hand,
                board,
            )
            private_cards = [card for card in score[2] if card in player.hand]
            player_results[player.name] = {
                "cards": private_cards,
                "hand_name": score[3],
                "score": score[:2],
                "best_five": list(score[2]),
            }
        return self._winning_details(board, player_results, "score")

    def hand_strength_score_details(self, active_players):
        player_results = {}
        for player in active_players:
            score = HandEvaluator.best_hand(player.hand)
            player_results[player.name] = {
                "cards": list(score[2]),
                "label": score[3],
                "rank": score[:2],
            }
        details = self._winning_details([], player_results, "rank")
        details.pop("board")
        return details

    @staticmethod
    def _winning_details(board: List[Card], player_results, score_key):
        from fractions import Fraction
        best = max(result[score_key] for result in player_results.values())
        winners = [
            name for name, result in player_results.items()
            if result[score_key] == best
        ]
        return {
            "board": list(board),
            "players": player_results,
            "winners": winners,
            "points": Fraction(1, len(winners)),
        }
