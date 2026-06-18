from dataclasses import dataclass


VALID_SUITS = {"hearts", "diamonds", "clubs", "spades"}
VALID_RANKS = {
    "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "J", "Q", "K", "A",
}


@dataclass(frozen=True, order=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self):
        if self.rank not in VALID_RANKS:
            raise ValueError(f"Invalid card rank: {self.rank}")

        if self.suit not in VALID_SUITS:
            raise ValueError(f"Invalid card suit: {self.suit}")

    def __str__(self) -> str:
        return f"{self.rank} of {self.suit}"