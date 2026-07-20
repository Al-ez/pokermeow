from typing import List

from nlh import money


class PotLimitBettingMixin:
    """Shared pot-limit constraints for poker engine variants."""

    def legal_actions(self, player_name: str) -> List[str]:
        actions = super().legal_actions(player_name)
        player = self._player_by_name(player_name)
        if "all_in" in actions and not self._can_move_all_in(player):
            actions.remove("all_in")
        return actions

    def act(self, player_name: str, action: str, amount=0):
        player = self._player_by_name(player_name)
        action = action.lower()
        amount = money(amount)

        if action == "bet":
            maximum = self.max_bet(player_name)
            if amount > maximum:
                raise ValueError(
                    f"Pot-limit bet cannot be more than {maximum}"
                )
        elif action == "raise":
            maximum = self.max_raise_total(player_name)
            if amount > maximum:
                raise ValueError(
                    f"Pot-limit raise cannot be more than {maximum}"
                )
        elif action == "all_in" and not self._can_move_all_in(player):
            maximum = self._all_in_limit(player_name)
            raise ValueError(
                f"All-in is above the pot-limit maximum of {maximum}"
            )

        return super().act(player_name, action, amount)

    def max_bet(self, player_name: str):
        player = self._player_by_name(player_name)
        if self.current_bet != 0:
            return 0
        return min(player.stack, max(self.big_blind, self.pot))

    def max_raise_total(self, player_name: str):
        player = self._player_by_name(player_name)
        to_call = self.current_bet - player.current_bet
        if self.current_bet <= 0 or to_call < 0:
            return 0

        pot_after_call = self.pot + to_call
        max_total = self.current_bet + pot_after_call
        affordable_total = player.current_bet + player.stack
        return min(max_total, affordable_total)

    def _all_in_limit(self, player_name: str):
        return self.max_raise_total(player_name)

    def _can_move_all_in(self, player) -> bool:
        if player.stack <= 0:
            return False
        if self.current_bet == 0:
            return player.stack <= self.max_bet(player.name)
        return (
            player.current_bet + player.stack
            <= self.max_raise_total(player.name)
        )
