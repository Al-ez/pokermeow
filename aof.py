from decimal import Decimal
from typing import Dict

from deck import Deck
from game_categories import BoardCategory
from nlh import ActionResult, NoLimitHoldemGame, ZERO, money


class AOFGame(NoLimitHoldemGame):
    board_category = BoardCategory.SINGLE_BOARD

    def __init__(
        self,
        player_stacks: Dict[str, Decimal],
        ante,
        multiplier,
        shuffle: bool = True,
    ):
        ante = money(ante)
        multiplier = money(multiplier)
        if ante <= 0:
            raise ValueError("Ante must be greater than zero")
        if multiplier < 10:
            raise ValueError("Multiplier must be at least 10")
        super().__init__(
            player_stacks,
            small_blind=ante,
            big_blind=ante * 2,
            shuffle=shuffle,
        )
        self.ante = ante
        self.multiplier = multiplier
        self.commitment_target = ante * multiplier
        self.discarded_players = set()

    def start_hand(self) -> None:
        self.deck = Deck(shuffle=self.shuffle)
        self.board = []
        self.pot = ZERO
        self.current_bet = self.ante
        self.min_raise = self.commitment_target - self.ante
        self.hand_active = True
        self.discarded_players = set()

        for player in self.players:
            player.reset_for_hand()

        self._deal_hole_cards()
        for player in self.players:
            self.pot += player.commit(self.ante)
        self.action_index = self._next_active_index(self.dealer_index)

    def _deal_hole_cards(self) -> None:
        for _ in range(3):
            for player in self.players:
                player.receive_card(self.deck.deal_one())

    def discard(self, player_name: str, card_index: int):
        player = self._player_by_name(player_name)
        if player_name in self.discarded_players:
            raise ValueError("Player has already discarded")
        if len(player.hand) != 3:
            raise ValueError("AOF players must have three cards before discarding")
        if card_index < 0 or card_index >= len(player.hand):
            raise ValueError("Discard choice is invalid")
        discarded = player.hand.pop(card_index)
        self.discarded_players.add(player_name)
        return discarded

    def legal_actions(self, player_name):
        player = self._player_by_name(player_name)
        if player_name not in self.discarded_players:
            return []
        if player.folded or player.all_in:
            return []
        return ["fold", "all_in"]

    def fixed_all_in_amount(self, player_name):
        player = self._player_by_name(player_name)
        remaining_to_target = max(
            ZERO,
            self.commitment_target - player.total_committed,
        )
        return min(player.stack, remaining_to_target)

    def act(self, player_name: str, action: str, amount=0):
        if not self.hand_active:
            raise RuntimeError("No active hand. Call start_hand() first.")
        if player_name not in self.discarded_players:
            raise ValueError("Player must discard before acting")

        player = self._player_by_name(player_name)
        if player.folded or player.all_in:
            raise ValueError("Player cannot act again")

        action = action.lower()
        if action == "fold":
            player.folded = True
            committed = ZERO
        elif action == "all_in":
            committed = player.commit(self.fixed_all_in_amount(player_name))
            self.pot += committed
            player.all_in = True
            player.current_bet = player.total_committed
            self.current_bet = max(self.current_bet, player.current_bet)
        else:
            raise ValueError("AOF players may only fold or move all in")

        return ActionResult(
            player=player.name,
            action=action,
            amount=committed,
            pot=self.pot,
            current_bet=self.current_bet,
        )
