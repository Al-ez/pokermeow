from decimal import Decimal
from itertools import combinations
from typing import Dict

from deck import Deck
from game_categories import BoardCategory
from nlh import ActionResult, HandEvaluator, ZERO, money
from plo import PotLimitOmahaGame


class PotOrFoldGame(PotLimitOmahaGame):
    """Bomb-pot Omaha where the only opening action is pot or fold."""

    board_category = BoardCategory.SINGLE_BOARD
    ALLOWED_HOLE_CARDS = (4, 5, 6)

    def __init__(
        self,
        player_stacks: Dict[str, Decimal],
        ante,
        hole_cards,
        shuffle: bool = True,
    ):
        ante = money(ante)
        hole_cards = int(hole_cards)
        if ante <= 0:
            raise ValueError("Ante must be greater than zero")
        if hole_cards not in self.ALLOWED_HOLE_CARDS:
            choices = ", ".join(str(value) for value in self.ALLOWED_HOLE_CARDS)
            raise ValueError(f"Hole cards must be one of: {choices}")

        super().__init__(
            player_stacks,
            small_blind=ante,
            big_blind=ante * 2,
            shuffle=shuffle,
        )
        self.ante = ante
        self.hole_card_count = hole_cards
        self.pot_opened = False

    def start_hand(self) -> None:
        self.deck = Deck(shuffle=self.shuffle)
        self.board = []
        self.pot = ZERO
        self.current_bet = ZERO
        self.min_raise = ZERO
        self.hand_active = True
        self.pot_opened = False

        for player in self.players:
            player.reset_for_hand()

        self._deal_hole_cards()
        for player in self.players:
            self.pot += player.commit(self.ante)
        self.action_index = self._next_active_index(self.dealer_index)

    def _deal_hole_cards(self) -> None:
        for _ in range(self.hole_card_count):
            for player in self.players:
                player.receive_card(self.deck.deal_one())

    def deal_flop(self):
        board = super().deal_flop()
        small_blind_index = self._small_blind_index()
        small_blind = self.players[small_blind_index]
        self.action_index = (
            small_blind_index
            if not small_blind.folded and not small_blind.all_in
            else self._next_active_index(small_blind_index)
        )
        return board

    def legal_actions(self, player_name):
        player = self._player_by_name(player_name)
        if player.folded or player.all_in:
            return []
        if not self.pot_opened:
            return ["fold", "pot"]
        return ["fold", "call"]

    def act(self, player_name: str, action: str, amount=0):
        if not self.hand_active:
            raise RuntimeError("No active hand. Call start_hand() first.")

        player = self._player_by_name(player_name)
        if player.folded or player.all_in:
            raise ValueError("Player cannot act again")

        action = action.lower()
        if action == "fold":
            player.folded = True
            committed = ZERO
        elif action == "pot":
            if self.pot_opened:
                raise ValueError("The pot has already been opened")
            committed = player.commit(self.pot)
            self.pot += committed
            self.current_bet = player.current_bet
            self.pot_opened = True
        elif action == "call":
            if not self.pot_opened:
                raise ValueError("Cannot call before the pot is opened")
            committed = player.commit(self.amount_to_call(player_name))
            self.pot += committed
        else:
            allowed = "fold or call" if self.pot_opened else "pot or fold"
            raise ValueError(f"POF players may only {allowed}")

        self.action_index = self._next_active_index(self.action_index)
        return ActionResult(
            player=player.name,
            action=action,
            amount=committed,
            pot=self.pot,
            current_bet=self.current_bet,
        )

    def _best_plo_hand(self, hole_cards, board):
        if len(hole_cards) != self.hole_card_count:
            raise ValueError(
                f"POF players must have exactly {self.hole_card_count} hole cards"
            )
        if len(board) != 5:
            raise ValueError("POF showdown requires exactly five board cards")

        best = None
        for hole_combo in combinations(hole_cards, 2):
            for board_combo in combinations(board, 3):
                cards = list(hole_combo + board_combo)
                score = HandEvaluator.evaluate_five(cards)
                if best is None or score[:2] > best[:2]:
                    best = score
        return best
