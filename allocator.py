from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, List, Tuple

from card import Card
from deck import Deck
from nlh import HandEvaluator, HandResult, NoLimitHoldemGame, RANK_VALUES, ZERO, money


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


class AllocatorGame(NoLimitHoldemGame):
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
        if self.bomb_pot_ante > 0:
            self.big_blind = self.bomb_pot_ante

    def start_hand(self) -> None:
        self.deck = Deck(shuffle=self.shuffle)
        self.board = []
        self.top_board = []
        self.bottom_board = []
        self.allocations = {}
        self.pot = ZERO
        self.current_bet = ZERO
        self.min_raise = self.big_blind
        self.hand_active = True

        for player in self.players:
            player.reset_for_hand()

        self._deal_hole_cards()
        self._post_bomb_pot_antes()
        self.action_index = self._next_active_index(self.dealer_index)

    def legal_actions(self, player_name: str) -> List[str]:
        actions = super().legal_actions(player_name)
        player = self._player_by_name(player_name)

        if "all_in" in actions and not self._can_move_all_in(player):
            actions.remove("all_in")

        return actions

    def act(self, player_name: str, action: str, amount: int = 0):
        player = self._player_by_name(player_name)
        action = action.lower()
        amount = money(amount)

        if action == "bet":
            max_bet = self.max_bet(player_name)
            if amount > max_bet:
                raise ValueError(f"Pot-limit bet cannot be more than {max_bet}")

        elif action == "raise":
            max_raise = self.max_raise_total(player_name)
            if amount > max_raise:
                raise ValueError(f"Pot-limit raise cannot be more than {max_raise}")

        elif action == "all_in" and not self._can_move_all_in(player):
            max_total = self.max_raise_total(player_name)
            if self.current_bet == 0:
                max_total = self.max_bet(player_name)
            raise ValueError(f"All-in is above the pot-limit maximum of {max_total}")

        return super().act(player_name, action, amount)

    def max_bet(self, player_name: str) -> int:
        player = self._player_by_name(player_name)
        if self.current_bet != 0:
            return 0

        return min(player.stack, max(self.big_blind, self.pot))

    def max_raise_total(self, player_name: str) -> int:
        player = self._player_by_name(player_name)
        to_call = self.current_bet - player.current_bet

        if self.current_bet <= 0 or to_call < 0:
            return 0

        pot_after_call = self.pot + to_call
        max_total = self.current_bet + pot_after_call
        affordable_total = player.current_bet + player.stack

        return min(max_total, affordable_total)

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

    def calculate_scores(self) -> Dict[str, AllocatorScore]:
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

        scores = self.calculate_scores()
        amount_won = {}
        winners_by_pot = self._award_showdown_pots(
            active_players,
            scores,
            amount_won,
            score_key=lambda score: (score.total,),
        )
        winners = list(dict.fromkeys(winners_by_pot))
        self.hand_active = False

        return HandResult(
            winners=winners,
            hand_name="allocator score",
            winning_cards=[],
            amount_won=amount_won,
        )

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

    def _can_move_all_in(self, player) -> bool:
        if player.stack <= 0:
            return False

        if self.current_bet == 0:
            return player.stack <= self.max_bet(player.name)

        return player.current_bet + player.stack <= self.max_raise_total(player.name)

    def _score_board(
        self,
        active_players,
        allocation_name: str,
        board: List[Card],
    ) -> Dict[str, Fraction]:
        board_scores = {}
        for player in active_players:
            allocation = self.allocations[player.name]
            allocated_cards = getattr(allocation, allocation_name)
            board_scores[player.name] = HandEvaluator.best_hand(allocated_cards + board)

        best_score = max(score[:2] for score in board_scores.values())
        winners = [
            player_name
            for player_name, score in board_scores.items()
            if score[:2] == best_score
        ]
        point = Fraction(1, len(winners))

        return {winner: point for winner in winners}

    def _score_hand_strength(self, active_players) -> Dict[str, Fraction]:
        strength_scores = {
            player.name: self.hand_strength_rank(self.allocations[player.name].hand)
            for player in active_players
        }
        best_score = max(strength_scores.values())
        winners = [
            player_name
            for player_name, score in strength_scores.items()
            if score == best_score
        ]
        point = Fraction(1, len(winners))

        return {winner: point for winner in winners}

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
