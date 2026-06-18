from itertools import combinations
from typing import Dict, List, Tuple

from card import Card
from nlh import HandEvaluator, NoLimitHoldemGame, money


class PotLimitOmahaGame(NoLimitHoldemGame):
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

    def _can_move_all_in(self, player) -> bool:
        if player.stack <= 0:
            return False

        if self.current_bet == 0:
            return player.stack <= self.max_bet(player.name)

        return player.current_bet + player.stack <= self.max_raise_total(player.name)
