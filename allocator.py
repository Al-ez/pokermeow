from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, List, Tuple

from card import Card
from deck import Deck
from nlh import HandEvaluator, HandResult, NoLimitHoldemGame, RANK_VALUES, ZERO
from pot_limit import PotLimitBettingMixin


@dataclass
class AllocatorScore:
    top_board_points: Fraction
    bottom_board_points: Fraction
    hand_strength_points: Fraction

    @property
    def total(self) -> Fraction:
        return (
            self.top_board_points
            + self.bottom_board_points
            + self.hand_strength_points
        )


@dataclass
class Allocation:
    top: List[Card]
    bottom: List[Card]
    hand: List[Card]


class AllocatorGame(PotLimitBettingMixin, NoLimitHoldemGame):
    def __init__(
        self,
        player_stacks: Dict[str, int],
        small_blind: int = 5,
        big_blind: int = 10,
        shuffle: bool = True,
        bomb_pot_ante: int = 0,
    ):
        super().__init__(player_stacks, small_blind, big_blind, shuffle)
        self.top_board: List[Card] = []
        self.bottom_board: List[Card] = []
        self.allocations: Dict[str, Allocation] = {}
        self.bomb_pot_ante = bomb_pot_ante
        self.pot_results = []
        if self.bomb_pot_ante > 0:
            self.big_blind = self.bomb_pot_ante

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
        self._post_bomb_pot_antes()
        self.action_index = self._next_active_index(self.dealer_index)

    def _all_in_limit(self, player_name: str):
        if self.current_bet == 0:
            return self.max_bet(player_name)
        return self.max_raise_total(player_name)

    def deal_flop(self) -> Tuple[List[Card], List[Card]]:
        self._reset_betting_round()
        self.deck.deal_one()
        self.top_board.extend([self.deck.deal_one() for _ in range(3)])
        self.bottom_board.extend([self.deck.deal_one() for _ in range(3)])
        self.board = list(self.top_board)
        return list(self.top_board), list(self.bottom_board)

    def deal_turn(self) -> Tuple[Card, Card]:
        if len(self.top_board) != 3 or len(self.bottom_board) != 3:
            raise RuntimeError("Flop must be dealt before the turn")

        self._reset_betting_round()
        self.deck.deal_one()
        top_card = self.deck.deal_one()
        bottom_card = self.deck.deal_one()
        self.top_board.append(top_card)
        self.bottom_board.append(bottom_card)
        self.board = list(self.top_board)
        return top_card, bottom_card

    def deal_river(self) -> Tuple[Card, Card]:
        if len(self.top_board) != 4 or len(self.bottom_board) != 4:
            raise RuntimeError("Turn must be dealt before the river")

        self._reset_betting_round()
        self.deck.deal_one()
        top_card = self.deck.deal_one()
        bottom_card = self.deck.deal_one()
        self.top_board.append(top_card)
        self.bottom_board.append(bottom_card)
        self.board = list(self.top_board)
        return top_card, bottom_card

    def set_allocation(
        self,
        player_name: str,
        top_cards: List[Card],
        bottom_cards: List[Card],
        hand_cards: List[Card],
    ) -> None:
        player = self._player_by_name(player_name)
        allocation = Allocation(
            top=list(top_cards),
            bottom=list(bottom_cards),
            hand=list(hand_cards),
        )
        self.validate_allocation(player.hand, allocation)
        self.allocations[player_name] = allocation

    def validate_allocation(self, player_cards: List[Card], allocation: Allocation) -> None:
        buckets = [allocation.top, allocation.bottom, allocation.hand]
        if any(len(bucket) != 2 for bucket in buckets):
            raise ValueError("Each allocation bucket must contain exactly two cards")

        allocated_cards = allocation.top + allocation.bottom + allocation.hand
        if len(set(allocated_cards)) != 6:
            raise ValueError("Allocation cannot use the same card more than once")

        if set(allocated_cards) != set(player_cards):
            raise ValueError("Allocation must use every private card exactly once")

    def calculate_scores(self, active_players=None) -> Dict[str, AllocatorScore]:
        if active_players is None:
            active_players = [player for player in self.players if not player.folded]

        if len(self.top_board) != 5 or len(self.bottom_board) != 5:
            raise RuntimeError("Allocator scoring requires complete top and bottom boards")

        missing_allocations = [
            player.name
            for player in active_players
            if player.name not in self.allocations
        ]
        if missing_allocations:
            raise RuntimeError(f"Missing allocations for: {', '.join(missing_allocations)}")

        top_points = self._score_board(active_players, "top", self.top_board)
        bottom_points = self._score_board(active_players, "bottom", self.bottom_board)
        hand_points = self._score_hand_strength(active_players)

        return {
            player.name: AllocatorScore(
                top_board_points=top_points.get(player.name, Fraction(0, 1)),
                bottom_board_points=bottom_points.get(player.name, Fraction(0, 1)),
                hand_strength_points=hand_points.get(player.name, Fraction(0, 1)),
            )
            for player in active_players
        }

    def showdown(self) -> HandResult:
        active_players = [player for player in self.players if not player.folded]

        if len(active_players) == 1:
            return super().showdown()

        amount_won = {}
        winners_by_pot = self._award_allocator_pots(active_players, amount_won)
        winners = list(dict.fromkeys(winners_by_pot))
        self.hand_active = False

        return HandResult(
            winners=winners,
            hand_name="allocator score",
            winning_cards=[],
            amount_won=amount_won,
        )

    def _award_allocator_pots(self, active_players, amount_won) -> List[str]:
        winners_by_pot = []
        self.pot_results = []
        committed_levels = sorted(
            {
                player.total_committed
                for player in self.players
                if player.total_committed > 0
            }
        )
        previous_level = ZERO
        pot_number = 0

        for level in committed_levels:
            contributors = [
                player
                for player in self.players
                if player.total_committed >= level
            ]
            pot_amount = (level - previous_level) * len(contributors)
            previous_level = level

            if pot_amount <= 0:
                continue

            eligible_players = [
                player
                for player in active_players
                if player.total_committed >= level
            ]

            if not eligible_players:
                continue

            pot_number += 1
            scores = self.calculate_scores(eligible_players)
            best_score = max(score.total for score in scores.values())
            pot_winners = [
                player
                for player in eligible_players
                if scores[player.name].total == best_score
            ]
            share = pot_amount / len(pot_winners)
            self.pot_results.append(
                {
                    "name": "Main pot" if pot_number == 1 else f"Side pot {pot_number - 1}",
                    "amount": pot_amount,
                    "eligible_players": [player.name for player in eligible_players],
                    "scores": scores,
                    "winners": [player.name for player in pot_winners],
                }
            )

            for winner in pot_winners:
                winner.stack += share
                amount_won[winner.name] = amount_won.get(winner.name, ZERO) + share
                winners_by_pot.append(winner.name)

        return winners_by_pot

    def table_state(self) -> Dict:
        state = super().table_state()
        state["top_board"] = list(self.top_board)
        state["bottom_board"] = list(self.bottom_board)
        return state

    def _deal_hole_cards(self) -> None:
        for _ in range(6):
            for player in self.players:
                player.receive_card(self.deck.deal_one())

    def _post_bomb_pot_antes(self) -> None:
        if self.bomb_pot_ante <= 0:
            return

        for player in self.players:
            self.pot += player.commit(self.bomb_pot_ante)

    def _score_board(
        self,
        active_players,
        allocation_name: str,
        board: List[Card],
    ) -> Dict[str, Fraction]:
        details = self.board_score_details(
            active_players,
            allocation_name,
            board,
        )
        return {
            winner: details["points"]
            for winner in details["winners"]
        }

    def board_score_details(
        self,
        active_players,
        allocation_name: str,
        board: List[Card],
    ) -> Dict:
        player_results = {}
        for player in active_players:
            allocation = self.allocations[player.name]
            allocated_cards = getattr(allocation, allocation_name)
            score = HandEvaluator.best_hand(allocated_cards + board)
            player_results[player.name] = {
                "cards": list(allocated_cards),
                "hand_name": score[3],
                "score": score[:2],
                "best_five": list(score[2]),
            }

        best_score = max(
            result["score"] for result in player_results.values()
        )
        winners = [
            player_name for player_name, result in player_results.items()
            if result["score"] == best_score
        ]
        return {
            "board": list(board),
            "players": player_results,
            "winners": winners,
            "points": Fraction(1, len(winners)),
        }

    def _score_hand_strength(self, active_players) -> Dict[str, Fraction]:
        details = self.hand_strength_score_details(active_players)
        return {
            winner: details["points"]
            for winner in details["winners"]
        }

    def hand_strength_score_details(self, active_players) -> Dict:
        player_results = {}
        for player in active_players:
            cards = self.allocations[player.name].hand
            player_results[player.name] = {
                "cards": list(cards),
                "label": (
                    "pair" if cards[0].rank == cards[1].rank
                    else "high card"
                ),
                "rank": self.hand_strength_rank(cards),
            }

        best_score = max(
            result["rank"] for result in player_results.values()
        )
        winners = [
            player_name for player_name, result in player_results.items()
            if result["rank"] == best_score
        ]
        return {
            "players": player_results,
            "winners": winners,
            "points": Fraction(1, len(winners)),
        }

    @staticmethod
    def hand_strength_rank(cards: List[Card]) -> Tuple[int, int, int]:
        if len(cards) != 2:
            raise ValueError("Hand strength requires exactly two cards")

        first = RANK_VALUES[cards[0].rank]
        second = RANK_VALUES[cards[1].rank]

        if first == second:
            return 1, first, 0

        high = max(first, second)
        low = min(first, second)
        return 0, high, low
