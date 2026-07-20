from typing import List, Tuple

from card import Card
from allocator import Allocation, AllocatorGame


class HelicopterGame(AllocatorGame):
    """Allocator bomb pot with equal private-card draws on turn and river."""

    MAX_STREET_DRAW = 3

    def start_hand(self) -> None:
        super().start_hand()
        self._reserved_river = []

    def act(self, player_name: str, action: str, amount=0):
        result = super().act(player_name, action, amount)
        if result.action == "fold":
            player = self._player_by_name(player_name)
            self.deck.cards.extend(player.hand)
            player.hand.clear()
            if self.shuffle:
                self.deck.shuffle()
        return result

    def deal_turn(self) -> Tuple[Card, Card]:
        cards = super().deal_turn()
        # Reserve the river burn and both river-board cards first. They are no
        # longer part of the drawable deck, so every remaining card can safely
        # participate in the equal turn draw.
        self._reserved_river = [self.deck.deal_one() for _ in range(3)]
        self._deal_equal_private_draw()
        return cards

    def deal_river(self) -> Tuple[Card, Card]:
        if len(self.top_board) != 4 or len(self.bottom_board) != 4:
            raise RuntimeError("Turn must be dealt before the river")
        if len(self._reserved_river) != 3:
            raise RuntimeError("River cards were not reserved on the turn")
        self._reset_betting_round()
        _, top_card, bottom_card = self._reserved_river
        self._reserved_river = []
        self.top_board.append(top_card)
        self.bottom_board.append(bottom_card)
        self.board = list(self.top_board)
        self._deal_equal_private_draw()
        return top_card, bottom_card

    def _deal_equal_private_draw(self, reserve: int = 0) -> int:
        players = self.active_players()
        if not players:
            return 0
        available = max(0, self.deck.remaining() - reserve)
        cards_each = min(self.MAX_STREET_DRAW, available // len(players))
        for _ in range(cards_each):
            for player in players:
                player.receive_card(self.deck.deal_one())
        return cards_each

    def validate_allocation(self, player_cards: List[Card], allocation: Allocation) -> None:
        buckets = [allocation.top, allocation.bottom, allocation.hand]
        if any(len(bucket) != 2 for bucket in buckets):
            raise ValueError("Each allocation bucket must contain exactly two cards")
        allocated_cards = allocation.top + allocation.bottom + allocation.hand
        if len(set(allocated_cards)) != 6:
            raise ValueError("Allocation cannot use the same card more than once")
        if not set(allocated_cards).issubset(set(player_cards)):
            raise ValueError("Allocation can only use cards in the player's hand")
