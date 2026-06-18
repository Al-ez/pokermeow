from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from card import Card
from deck import Deck
from player import Player


RANK_VALUES = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}


ZERO = Decimal("0")


def money(value) -> Decimal:
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Amount must be a valid number")

    if not amount.is_finite():
        raise ValueError("Amount must be a valid number")

    return amount


@dataclass
class NLHPlayer(Player):
    stack: Decimal = Decimal("1000")
    folded: bool = False
    all_in: bool = False
    current_bet: Decimal = ZERO
    total_committed: Decimal = ZERO

    def __init__(self, name: str, stack=1000):
        super().__init__(name)
        stack = money(stack)
        if stack <= 0:
            raise ValueError("Player stack must be greater than zero")

        self.stack = stack
        self.folded = False
        self.all_in = False
        self.current_bet = ZERO
        self.total_committed = ZERO

    def reset_for_hand(self) -> None:
        self.clear_hand()
        self.folded = False
        self.all_in = False
        self.current_bet = ZERO
        self.total_committed = ZERO

    def commit(self, amount) -> Decimal:
        amount = money(amount)
        if amount < 0:
            raise ValueError("Cannot commit a negative amount")

        committed = min(amount, self.stack)
        self.stack -= committed
        self.current_bet += committed
        self.total_committed += committed

        if self.stack == ZERO:
            self.all_in = True

        return committed


@dataclass
class ActionResult:
    player: str
    action: str
    amount: Decimal
    pot: Decimal
    current_bet: Decimal


@dataclass
class HandResult:
    winners: List[str]
    hand_name: str
    winning_cards: List[Card]
    amount_won: Dict[str, Decimal]


class HandEvaluator:
    @classmethod
    def best_hand(cls, cards: List[Card]) -> Tuple[int, List[int], List[Card], str]:
        if len(cards) < 5:
            raise ValueError("At least five cards are required to evaluate a hand")

        best = None

        for hand in combinations(cards, 5):
            score = cls.evaluate_five(list(hand))
            if best is None or score[:2] > best[:2]:
                best = score

        return best

    @staticmethod
    def evaluate_five(cards: List[Card]) -> Tuple[int, List[int], List[Card], str]:
        values = sorted((RANK_VALUES[card.rank] for card in cards), reverse=True)
        suits = [card.suit for card in cards]
        counts = {value: values.count(value) for value in set(values)}

        flush = len(set(suits)) == 1
        straight_high = HandEvaluator._straight_high(values)

        grouped = sorted(
            counts.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )

        if flush and straight_high:
            return 8, [straight_high], cards, "straight flush"

        if grouped[0][1] == 4:
            quad = grouped[0][0]
            kicker = max(value for value in values if value != quad)
            return 7, [quad, kicker], cards, "four of a kind"

        if grouped[0][1] == 3 and grouped[1][1] == 2:
            return 6, [grouped[0][0], grouped[1][0]], cards, "full house"

        if flush:
            return 5, values, cards, "flush"

        if straight_high:
            return 4, [straight_high], cards, "straight"

        if grouped[0][1] == 3:
            trips = grouped[0][0]
            kickers = sorted(
                [value for value in values if value != trips],
                reverse=True,
            )
            return 3, [trips] + kickers, cards, "three of a kind"

        pairs = [value for value, count in grouped if count == 2]
        if len(pairs) == 2:
            high_pair, low_pair = sorted(pairs, reverse=True)
            kicker = max(value for value in values if value not in pairs)
            return 2, [high_pair, low_pair, kicker], cards, "two pair"

        if len(pairs) == 1:
            pair = pairs[0]
            kickers = sorted(
                [value for value in values if value != pair],
                reverse=True,
            )
            return 1, [pair] + kickers, cards, "one pair"

        return 0, values, cards, "high card"

    @staticmethod
    def _straight_high(values: List[int]) -> Optional[int]:
        unique_values = sorted(set(values), reverse=True)

        if {14, 5, 4, 3, 2}.issubset(unique_values):
            return 5

        for index in range(len(unique_values) - 4):
            window = unique_values[index:index + 5]
            if window[0] - window[4] == 4:
                return window[0]

        return None


class NoLimitHoldemGame:
    def __init__(
        self,
        player_stacks: Dict[str, Decimal],
        small_blind=5,
        big_blind=10,
        shuffle: bool = True,
    ):
        small_blind = money(small_blind)
        big_blind = money(big_blind)
        if len(player_stacks) < 2:
            raise ValueError("Texas Hold'em requires at least two players")

        if small_blind <= 0 or big_blind <= 0:
            raise ValueError("Blinds must be greater than zero")

        if small_blind >= big_blind:
            raise ValueError("Small blind must be less than big blind")

        self.players = [
            NLHPlayer(name, stack)
            for name, stack in player_stacks.items()
        ]
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.shuffle = shuffle
        self.dealer_index = 0

        self.deck = Deck(shuffle=shuffle)
        self.board: List[Card] = []
        self.pot = ZERO
        self.current_bet = ZERO
        self.min_raise = big_blind
        self.action_index = 0
        self.hand_active = False

    def start_hand(self) -> None:
        self.deck = Deck(shuffle=self.shuffle)
        self.board = []
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

    def legal_actions(self, player_name: str) -> List[str]:
        player = self._player_by_name(player_name)

        if player.folded or player.all_in:
            return []

        to_call = self.current_bet - player.current_bet
        actions = ["fold"]

        if to_call == 0:
            actions.append("check")
            if self.current_bet == 0 and player.stack > 0:
                actions.append("bet")
            elif self.current_bet > 0 and player.stack > 0:
                actions.append("raise")
        else:
            actions.append("call")
            if player.stack > to_call:
                actions.append("raise")

        if player.stack > 0:
            actions.append("all_in")

        return actions

    def act(self, player_name: str, action: str, amount=0) -> ActionResult:
        if not self.hand_active:
            raise RuntimeError("No active hand. Call start_hand() first.")

        player = self._player_by_name(player_name)
        if player.folded:
            raise ValueError("Folded players cannot act")

        if player.all_in:
            raise ValueError("All-in players cannot act")

        action = action.lower()
        amount = money(amount)
        to_call = self.current_bet - player.current_bet

        if action == "fold":
            player.folded = True
            committed = ZERO

        elif action == "check":
            if to_call != 0:
                raise ValueError("Cannot check when facing a bet")
            committed = ZERO

        elif action == "call":
            if to_call <= 0:
                raise ValueError("Cannot call when there is no bet")
            committed = player.commit(to_call)
            self.pot += committed

        elif action == "bet":
            if self.current_bet != 0:
                raise ValueError("Use raise when a bet already exists")
            if amount < self.big_blind:
                raise ValueError("Opening bet must be at least the big blind")
            committed = player.commit(amount)
            self.pot += committed
            self.current_bet = player.current_bet
            self.min_raise = amount

        elif action == "raise":
            if self.current_bet <= 0:
                raise ValueError("Cannot raise when there is no bet to call")
            total_bet = amount
            raise_size = total_bet - self.current_bet

            if total_bet <= self.current_bet:
                raise ValueError("Raise must be greater than the current bet")

            if raise_size < self.min_raise and total_bet < player.current_bet + player.stack:
                raise ValueError("Raise must be at least the minimum raise")

            committed = player.commit(total_bet - player.current_bet)
            self.pot += committed

            if player.current_bet > self.current_bet:
                self.min_raise = player.current_bet - self.current_bet
                self.current_bet = player.current_bet

        elif action == "all_in":
            committed = player.commit(player.stack)
            self.pot += committed

            if player.current_bet > self.current_bet:
                self.min_raise = player.current_bet - self.current_bet
                self.current_bet = player.current_bet

        else:
            raise ValueError(f"Unknown action: {action}")

        self.action_index = self._next_active_index(self.action_index)

        return ActionResult(
            player=player.name,
            action=action,
            amount=committed,
            pot=self.pot,
            current_bet=self.current_bet,
        )

    def deal_flop(self) -> List[Card]:
        self._reset_betting_round()
        self.deck.deal_one()
        self.board.extend([self.deck.deal_one() for _ in range(3)])
        return list(self.board)

    def deal_turn(self) -> Card:
        if len(self.board) != 3:
            raise RuntimeError("Flop must be dealt before the turn")

        self._reset_betting_round()
        self.deck.deal_one()
        card = self.deck.deal_one()
        self.board.append(card)
        return card

    def deal_river(self) -> Card:
        if len(self.board) != 4:
            raise RuntimeError("Turn must be dealt before the river")

        self._reset_betting_round()
        self.deck.deal_one()
        card = self.deck.deal_one()
        self.board.append(card)
        return card

    def showdown(self) -> HandResult:
        active_players = [player for player in self.players if not player.folded]

        if len(active_players) == 1:
            winner = active_players[0]
            winner.stack += self.pot
            result = HandResult(
                winners=[winner.name],
                hand_name="uncontested",
                winning_cards=[],
                amount_won={winner.name: self.pot},
            )
            self.hand_active = False
            return result

        if len(self.board) != 5:
            raise RuntimeError("Showdown requires a complete five-card board")

        scores = {}
        for player in active_players:
            scores[player.name] = HandEvaluator.best_hand(player.hand + self.board)

        amount_won: Dict[str, Decimal] = {}
        winners_by_pot = self._award_showdown_pots(active_players, scores, amount_won)
        winners = list(dict.fromkeys(winners_by_pot))
        best_overall_score = max(scores[player.name][:2] for player in active_players)
        best_overall_winner = next(
            player
            for player in active_players
            if scores[player.name][:2] == best_overall_score
        )
        first_winner_score = scores[best_overall_winner.name]

        self.hand_active = False

        return HandResult(
            winners=winners,
            hand_name=first_winner_score[3],
            winning_cards=list(first_winner_score[2]),
            amount_won=amount_won,
        )

    def advance_dealer(self) -> None:
        self.dealer_index = (self.dealer_index + 1) % len(self.players)

    def active_players(self) -> List[NLHPlayer]:
        return [player for player in self.players if not player.folded]

    def table_state(self) -> Dict:
        return {
            "pot": self.pot,
            "board": list(self.board),
            "current_bet": self.current_bet,
            "players": {
                player.name: {
                    "stack": player.stack,
                    "hand": list(player.hand),
                    "folded": player.folded,
                    "all_in": player.all_in,
                    "current_bet": player.current_bet,
                    "total_committed": player.total_committed,
                }
                for player in self.players
            },
        }

    def _award_showdown_pots(
        self,
        active_players: List[NLHPlayer],
        scores: Dict[str, Tuple[int, List[int], List[Card], str]],
        amount_won: Dict[str, Decimal],
        score_key=None,
    ) -> List[str]:
        if score_key is None:
            score_key = lambda score: score[:2]

        winners_by_pot = []
        committed_levels = sorted(
            {
                player.total_committed
                for player in self.players
                if player.total_committed > 0
            }
        )
        previous_level = ZERO

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

            best_score = max(score_key(scores[player.name]) for player in eligible_players)
            pot_winners = [
                player
                for player in eligible_players
                if score_key(scores[player.name]) == best_score
            ]

            share = pot_amount / Decimal(len(pot_winners))

            for winner in pot_winners:
                won = share
                winner.stack += won
                amount_won[winner.name] = amount_won.get(winner.name, ZERO) + won
                winners_by_pot.append(winner.name)

        return winners_by_pot

    def _deal_hole_cards(self) -> None:
        for _ in range(2):
            for player in self.players:
                player.receive_card(self.deck.deal_one())

    def _post_blinds(self) -> None:
        small_blind_player = self.players[self._small_blind_index()]
        big_blind_player = self.players[self._big_blind_index()]

        self.pot += small_blind_player.commit(self.small_blind)
        self.pot += big_blind_player.commit(self.big_blind)

        self.current_bet = big_blind_player.current_bet

    def _reset_betting_round(self) -> None:
        for player in self.players:
            player.current_bet = ZERO

        self.current_bet = ZERO
        self.min_raise = self.big_blind
        self.action_index = self._next_active_index(self.dealer_index)

    def _small_blind_index(self) -> int:
        if len(self.players) == 2:
            return self.dealer_index

        return (self.dealer_index + 1) % len(self.players)

    def _big_blind_index(self) -> int:
        if len(self.players) == 2:
            return (self.dealer_index + 1) % len(self.players)

        return (self.dealer_index + 2) % len(self.players)

    def _next_active_index(self, start_index: int) -> int:
        for offset in range(1, len(self.players) + 1):
            index = (start_index + offset) % len(self.players)
            player = self.players[index]

            if not player.folded and not player.all_in:
                return index

        return start_index

    def _player_by_name(self, name: str) -> NLHPlayer:
        for player in self.players:
            if player.name == name:
                return player

        raise ValueError(f"Unknown player: {name}")
