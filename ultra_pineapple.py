from pineapple import PineappleGame
from nlh import NoLimitHoldemGame


class UltraPineappleGame(PineappleGame):
    """Five-card Pineapple with one mandatory discard on every street."""

    DISCARD_STREETS = {3: "flop", 4: "turn", 5: "river"}

    def start_hand(self):
        super().start_hand()
        self.discarded_streets = {
            player.name: set()
            for player in self.players
        }

    def _deal_hole_cards(self):
        for _ in range(5):
            for player in self.players:
                player.receive_card(self.deck.deal_one())

    def current_discard_street(self):
        return self.DISCARD_STREETS.get(len(self.board))

    def discard(self, player_name, card_index):
        player = self._player_by_name(player_name)
        street = self.current_discard_street()
        if street is None:
            raise ValueError("Ultra Pineapple discards happen after a board street")
        if street in self.discarded_streets[player_name]:
            raise ValueError(f"Player has already discarded on the {street}")

        expected_cards = {"flop": 5, "turn": 4, "river": 3}[street]
        if len(player.hand) != expected_cards:
            raise ValueError(
                f"Player must have {expected_cards} cards before the {street} discard"
            )
        if card_index < 0 or card_index >= len(player.hand):
            raise ValueError("Discard choice is invalid")

        discarded = player.hand.pop(card_index)
        self.discarded_streets[player_name].add(street)
        return discarded

    def has_discarded_current_street(self, player_name):
        street = self.current_discard_street()
        return (
            street is not None
            and street in self.discarded_streets[player_name]
        )

    def legal_actions(self, player_name):
        if not self.has_discarded_current_street(player_name):
            return []
        return NoLimitHoldemGame.legal_actions(self, player_name)

    def act(self, player_name, action, amount=0):
        if not self.has_discarded_current_street(player_name):
            raise ValueError("Player must discard on this street before acting")
        return NoLimitHoldemGame.act(self, player_name, action, amount)
