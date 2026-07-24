from decimal import Decimal
from typing import Dict, List, Tuple

from card import Card
from deck import Deck
from game_categories import BoardCategory
from nlh import NoLimitHoldemGame, ZERO, money


class PineappleGame(NoLimitHoldemGame):
    """Double-board bomb-pot Hold'em with a mandatory pre-action discard."""

    board_category = BoardCategory.DOUBLE_BOARD

    def __init__(
        self,
        player_stacks: Dict[str, Decimal],
        ante,
        shuffle: bool = True,
    ):
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
        self.discarded_players = set()

    def start_hand(self) -> None:
        self.deck = Deck(shuffle=self.shuffle)
        self.board = []
        self.top_board = []
        self.bottom_board = []
        self.discarded_players = set()
        self.pot = ZERO
        self.current_bet = ZERO
        self.min_raise = self.big_blind
        self.hand_active = True

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
            raise ValueError("Pineapple players must have three cards before discarding")
        if card_index < 0 or card_index >= len(player.hand):
            raise ValueError("Discard choice is invalid")
        discarded = player.hand.pop(card_index)
        self.discarded_players.add(player_name)
        return discarded

    def legal_actions(self, player_name):
        if player_name not in self.discarded_players:
            return []
        return super().legal_actions(player_name)

    def act(self, player_name: str, action: str, amount=0):
        if player_name not in self.discarded_players:
            raise ValueError("Player must discard before acting")
        return super().act(player_name, action, amount)

    def deal_flop(self) -> Tuple[List[Card], List[Card]]:
        self._reset_betting_round()
        self.deck.deal_one()
        self.top_board.extend([self.deck.deal_one() for _ in range(3)])
        self.bottom_board.extend([self.deck.deal_one() for _ in range(3)])
        self.board = list(self.top_board)
        return list(self.top_board), list(self.bottom_board)

    def deal_turn(self) -> Tuple[Card, Card]:
        if len(self.top_board) != 3 or len(self.bottom_board) != 3:
            raise RuntimeError("Flops must be dealt before the turns")
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
            raise RuntimeError("Turns must be dealt before the rivers")
        self._reset_betting_round()
        self.deck.deal_one()
        top_card = self.deck.deal_one()
        bottom_card = self.deck.deal_one()
        self.top_board.append(top_card)
        self.bottom_board.append(bottom_card)
        self.board = list(self.top_board)
        return top_card, bottom_card

    def showdown(self):
        if len(self.active_players()) <= 1:
            return super().showdown()
        return self.showdown_boards([self.top_board, self.bottom_board])
