class Player:
    def __init__(self, name: str):
        if not name:
            raise ValueError("Player name cannot be empty")

        self.name = name
        self.hand = []

    def receive_card(self, card) -> None:
        self.hand.append(card)

    def clear_hand(self) -> None:
        self.hand.clear()

    def hand_size(self) -> int:
        return len(self.hand)

    def __repr__(self) -> str:
        return f"Player(name={self.name!r}, hand={self.hand!r})"