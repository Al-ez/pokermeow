import random

from card import Card, VALID_RANKS, VALID_SUITS


class Deck:
    def __init__(self, shuffle: bool = True):
        self.cards = [
            Card(rank, suit)
            for suit in sorted(VALID_SUITS)
            for rank in sorted(VALID_RANKS, key=self._rank_sort_key)
        ]

        if shuffle:
            self.shuffle()

    def shuffle(self) -> None:
        random.shuffle(self.cards)

    def deal_one(self) -> Card:
        if not self.cards:
            raise IndexError("Cannot deal from an empty deck")

        return self.cards.pop()

    def remaining(self) -> int:
        return len(self.cards)

    @staticmethod
    def _rank_sort_key(rank: str) -> int:
        order = {
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "10": 10,
            "J": 11,
            "Q": 12,
            "K": 13,
            "A": 14,
        }
        return order[rank]