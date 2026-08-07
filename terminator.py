from decimal import Decimal
from typing import Dict, List, Tuple

from card import Card
from deck import Deck
from game_categories import BoardCategory
from nlh import HandEvaluator, HandResult, NoLimitHoldemGame, RANK_VALUES, ZERO, money


class TerminatorGame(NoLimitHoldemGame):
    """Six-card double-board bomb pot where one board destroys ranks."""

    board_category = BoardCategory.DOUBLE_BOARD

    def __init__(self, player_stacks: Dict[str, Decimal], ante, shuffle=True):
        ante = money(ante)
        if ante <= 0:
            raise ValueError("Ante must be greater than zero")
        super().__init__(
            player_stacks,
            small_blind=ante / Decimal(2),
            big_blind=ante,
            shuffle=shuffle,
        )
        self.ante = ante
        self.top_board: List[Card] = []
        self.bottom_board: List[Card] = []
        self.terminated_board = None
        self.terminated_ranks = set()
        self.street = 0

    def start_hand(self):
        self.deck = Deck(shuffle=self.shuffle)
        self.board = []
        self.top_board = []
        self.bottom_board = []
        self.terminated_board = None
        self.terminated_ranks = set()
        self.street = 0
        self.pot = ZERO
        self.current_bet = ZERO
        self.min_raise = self.big_blind
        self.hand_active = True
        for player in self.players:
            player.reset_for_hand()
        for _ in range(6):
            for player in self.players:
                player.receive_card(self.deck.deal_one())
        for player in self.players:
            self.pot += player.commit(self.ante)
        self.action_index = self._next_active_index(self.dealer_index)

    def deal_flop(self) -> Tuple[List[Card], List[Card]]:
        self._reset_betting_round()
        self.deck.deal_one()
        self.top_board.extend(self.deck.deal_one() for _ in range(3))
        self.bottom_board.extend(self.deck.deal_one() for _ in range(3))
        self.street = 3
        return list(self.top_board), list(self.bottom_board)

    def choose_terminated_board(self, choice):
        if self.terminated_board is not None:
            raise ValueError("A board has already been terminated")
        if len(self.top_board) != 3 or len(self.bottom_board) != 3:
            raise RuntimeError("Both flops must be dealt before termination")
        choice = str(choice).lower()
        if choice not in {"top", "bottom"}:
            raise ValueError("Terminated board must be top or bottom")
        self.terminated_board = choice
        source = self.top_board if choice == "top" else self.bottom_board
        self.terminated_ranks.update(card.rank for card in source)
        self._apply_termination()

    @property
    def live_board(self):
        if self.terminated_board == "top":
            return self.bottom_board
        if self.terminated_board == "bottom":
            return self.top_board
        return []

    def _apply_termination(self):
        for player in self.players:
            player.hand[:] = [
                card for card in player.hand
                if card.rank not in self.terminated_ranks
            ]
        live = self.live_board
        live[:] = [card for card in live if card.rank not in self.terminated_ranks]
        self.board = list(live)

    def _deal_street(self):
        if self.terminated_board is None:
            raise RuntimeError("The dealer must terminate a board first")
        self._reset_betting_round()
        self.deck.deal_one()
        top_card = self.deck.deal_one()
        bottom_card = self.deck.deal_one()
        self.top_board.append(top_card)
        self.bottom_board.append(bottom_card)
        source_card = top_card if self.terminated_board == "top" else bottom_card
        self.terminated_ranks.add(source_card.rank)
        self._apply_termination()
        return top_card, bottom_card

    def deal_turn(self):
        if self.street != 3:
            raise RuntimeError("Flops must be dealt before the turns")
        cards = self._deal_street()
        self.street = 4
        return cards

    def deal_river(self):
        if self.street != 4:
            raise RuntimeError("Turns must be dealt before the rivers")
        cards = self._deal_street()
        self.street = 5
        return cards

    def _score_hand(self, hole_cards, board):
        cards = list(hole_cards) + list(board)
        if len(cards) >= 5:
            return HandEvaluator.best_hand(cards)
        if not cards:
            return -1, [], [], "no cards"
        values = sorted((RANK_VALUES[card.rank] for card in cards), reverse=True)
        counts = {value: values.count(value) for value in set(values)}
        grouped = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
        pairs = sorted((value for value, count in grouped if count == 2), reverse=True)
        if grouped[0][1] == 4:
            score, name = 7, "four of a kind"
        elif grouped[0][1] == 3:
            score, name = 3, "three of a kind"
        elif len(pairs) == 2:
            score, name = 2, "two pair"
        elif pairs:
            score, name = 1, "one pair"
        else:
            score, name = 0, "high card"
        tiebreak = [value for value, count in grouped for _ in range(count)]
        return score, tiebreak, cards, name

    def showdown(self) -> HandResult:
        active = [player for player in self.players if not player.folded]
        if len(active) <= 1:
            return super().showdown()
        scores = {player.name: self._score_hand(player.hand, self.board) for player in active}
        amount_won = {}
        winners_by_pot = self._award_showdown_pots(active, scores, amount_won)
        best = max(scores.values(), key=lambda score: score[:2])
        self.hand_active = False
        return HandResult(
            winners=list(dict.fromkeys(winners_by_pot)),
            hand_name=best[3],
            winning_cards=list(best[2]),
            amount_won=amount_won,
        )
