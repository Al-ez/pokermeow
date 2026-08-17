from itertools import combinations
from typing import Dict, List, Tuple

from card import Card
from game_categories import BoardCategory
from nlh import HandEvaluator, NoLimitHoldemGame
from nlh import ZERO
from deck import Deck
from pot_limit import PotLimitBettingMixin


class PotLimitOmahaGame(PotLimitBettingMixin, NoLimitHoldemGame):
    board_category = BoardCategory.SINGLE_BOARD
    ALLOWED_HOLE_CARDS = {4, 5, 6}
    ALLOWED_BOARDS = {1, 2}
    ALLOWED_MODES = {"preflop", "bomb_pot"}

    def __init__(
        self,
        player_stacks,
        small_blind=1,
        big_blind=2,
        hole_cards=4,
        boards=1,
        mode="preflop",
        ante_bb=1,
        shuffle=True,
    ):
        if hole_cards not in self.ALLOWED_HOLE_CARDS:
            raise ValueError("PLO hole cards must be 4, 5, or 6")
        if boards not in self.ALLOWED_BOARDS:
            raise ValueError("PLO boards must be 1 or 2")
        if mode not in self.ALLOWED_MODES:
            raise ValueError("PLO mode must be preflop or bomb_pot")
        if isinstance(ante_bb, bool) or not isinstance(ante_bb, int) or ante_bb <= 0:
            raise ValueError("PLO bomb-pot ante must be a positive whole number of BB")
        super().__init__(player_stacks, small_blind, big_blind, shuffle)
        self.hole_card_count = hole_cards
        self.board_count = boards
        self.mode = mode
        self.ante_bb = ante_bb
        self.board_category = (
            BoardCategory.DOUBLE_BOARD if boards == 2
            else BoardCategory.SINGLE_BOARD
        )
        if boards == 2:
            self.top_board = []
            self.bottom_board = []

    def start_hand(self):
        if self.mode == "preflop":
            super().start_hand()
        else:
            self.deck = Deck(shuffle=self.shuffle)
            self.board = []
            self.pot = ZERO
            self.current_bet = ZERO
            self.min_raise = self.big_blind
            self.hand_active = True
            for player in self.players:
                player.reset_for_hand()
            self._deal_hole_cards()
            for player in self.players:
                self.pot += player.commit(self.big_blind * self.ante_bb)
            self.action_index = self._next_active_index(self.dealer_index)
        if self.board_count == 2:
            self.top_board = []
            self.bottom_board = []

    def showdown(self):
        active_players = [player for player in self.players if not player.folded]

        if len(active_players) == 1:
            return super().showdown()

        if self.board_count == 2:
            return self.showdown_boards([self.top_board, self.bottom_board])

        if len(self.board) != 5:
            raise RuntimeError("Showdown requires a complete five-card board")

        scores = {}
        for player in active_players:
            scores[player.name] = self._best_plo_hand(player.hand, self.board)

        amount_won = {}
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

        from nlh import HandResult

        return HandResult(
            winners=winners,
            hand_name=first_winner_score[3],
            winning_cards=list(first_winner_score[2]),
            amount_won=amount_won,
        )

    def _deal_hole_cards(self) -> None:
        for _ in range(self.hole_card_count):
            for player in self.players:
                player.receive_card(self.deck.deal_one())

    def deal_flop(self):
        if self.board_count == 1:
            return super().deal_flop()
        self._reset_betting_round()
        self.deck.deal_one()
        self.top_board.extend(self.deck.deal_one() for _ in range(3))
        self.bottom_board.extend(self.deck.deal_one() for _ in range(3))
        self.board = list(self.top_board)
        return list(self.top_board), list(self.bottom_board)

    def deal_turn(self):
        if self.board_count == 1:
            return super().deal_turn()
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

    def deal_river(self):
        if self.board_count == 1:
            return super().deal_river()
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

    def _best_plo_hand(
        self,
        hole_cards: List[Card],
        board: List[Card],
    ) -> Tuple[int, List[int], List[Card], str]:
        if len(hole_cards) != self.hole_card_count:
            raise ValueError(
                f"PLO players must have exactly {self.hole_card_count} hole cards"
            )

        return self._best_plo_hand_from_available(hole_cards, board)

    @staticmethod
    def _best_plo_hand_from_available(
        hole_cards: List[Card],
        board: List[Card],
    ) -> Tuple[int, List[int], List[Card], str]:
        """Evaluate PLO using exactly two of any available private cards."""
        if len(hole_cards) < 2:
            raise ValueError("PLO requires at least two private cards")

        if len(board) != 5:
            raise ValueError("PLO showdown requires exactly five board cards")

        best = None
        for hole_combo in combinations(hole_cards, 2):
            for board_combo in combinations(board, 3):
                cards = list(hole_combo + board_combo)
                score = HandEvaluator.evaluate_five(cards)
                if best is None or score[:2] > best[:2]:
                    best = score

        return best

    def _score_hand(self, hole_cards: List[Card], board: List[Card]):
        return self._best_plo_hand(hole_cards, board)
