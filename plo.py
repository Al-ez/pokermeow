from itertools import combinations
from typing import Dict, List, Tuple

from card import Card
from nlh import HandEvaluator, NoLimitHoldemGame
from pot_limit import PotLimitBettingMixin


class PotLimitOmahaGame(PotLimitBettingMixin, NoLimitHoldemGame):
    def showdown(self):
        active_players = [player for player in self.players if not player.folded]

        if len(active_players) == 1:
            return super().showdown()

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
        for _ in range(4):
            for player in self.players:
                player.receive_card(self.deck.deal_one())

    def _best_plo_hand(
        self,
        hole_cards: List[Card],
        board: List[Card],
    ) -> Tuple[int, List[int], List[Card], str]:
        if len(hole_cards) != 4:
            raise ValueError("PLO players must have exactly four hole cards")

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
