from decimal import Decimal

from card import Card
from game_categories import BoardCategory
from nlh import NoLimitHoldemGame
from server import PokerTableSession, run_count_for_votes


def c(rank, suit):
    return Card(rank, suit)


def test_two_board_showdown_splits_the_pot_between_board_winners():
    game = NoLimitHoldemGame({"Alice": 100, "Bob": 100}, shuffle=False)
    alice, bob = game.players
    alice.hand = [c("A", "spades"), c("A", "hearts")]
    bob.hand = [c("K", "spades"), c("K", "hearts")]
    for player in game.players:
        player.stack = Decimal(0)
        player.total_committed = Decimal(100)
        player.all_in = True
    game.pot = Decimal(200)
    game.board = [
        c("2", "clubs"),
        c("3", "diamonds"),
        c("4", "hearts"),
        c("8", "spades"),
        c("9", "clubs"),
    ]
    second_board = [
        c("K", "clubs"),
        c("3", "clubs"),
        c("4", "diamonds"),
        c("8", "hearts"),
        c("9", "diamonds"),
    ]

    result = game.showdown_boards([game.board, second_board])

    assert result.amount_won == {
        "Alice": Decimal(100),
        "Bob": Decimal(100),
    }
    assert alice.stack == Decimal(100)
    assert bob.stack == Decimal(100)


def test_one_board_showdown_boards_matches_normal_full_pot_award():
    game = NoLimitHoldemGame({"Alice": 100, "Bob": 100}, shuffle=False)
    alice, bob = game.players
    alice.hand = [c("A", "spades"), c("A", "hearts")]
    bob.hand = [c("K", "spades"), c("K", "hearts")]
    for player in game.players:
        player.stack = Decimal(0)
        player.total_committed = Decimal(100)
    game.pot = Decimal(200)
    board = [
        c("2", "clubs"),
        c("3", "diamonds"),
        c("4", "hearts"),
        c("8", "spades"),
        c("9", "clubs"),
    ]

    result = game.showdown_boards([board])

    assert result.amount_won == {"Alice": Decimal(200)}


def test_run_it_twice_requires_every_active_player_to_choose_twice():
    players = {"Alice", "Bob", "Cara"}

    assert run_count_for_votes(
        players,
        {"Alice": "twice", "Bob": "twice", "Cara": "twice"},
    ) == 2
    assert run_count_for_votes(
        players,
        {"Alice": "twice", "Bob": "once", "Cara": "twice"},
    ) == 1
    assert run_count_for_votes(
        players,
        {"Alice": "twice", "Bob": "twice"},
    ) == 1


class FakeRunoutGame:
    board_category = BoardCategory.SINGLE_BOARD

    def __init__(self, board=None):
        self.board = list(board or [])
        self.next_card = 0

    def _cards(self, count):
        ranks = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
        cards = [
            c(ranks[(self.next_card + offset) % len(ranks)], "clubs")
            for offset in range(count)
        ]
        self.next_card += count
        return cards

    def deal_flop(self):
        self.board.extend(self._cards(3))

    def deal_turn(self):
        self.board.extend(self._cards(1))

    def deal_river(self):
        self.board.extend(self._cards(1))


def runout_session(monkeypatch, run_count, starting_board=None):
    session = object.__new__(PokerTableSession)
    session.game = FakeRunoutGame(starting_board)
    session.game_class = NoLimitHoldemGame
    session._request_run_it_vote = lambda clients: run_count
    events = []
    session.runout_snapshots = []

    def record_state(clients):
        events.append(("state", len(session.game.board)))
        current_runouts = getattr(session, "_current_runout_boards", None)
        session.runout_snapshots.append(
            [len(board) for board in current_runouts]
            if current_runouts
            else None
        )

    session._send_states_to = record_state
    session._broadcast_hand_message = lambda clients, message: events.append(
        ("message", message)
    )
    monkeypatch.setattr(
        "server.time.sleep",
        lambda seconds: events.append(("sleep", seconds)),
    )
    return session, events


def test_single_all_in_runout_reveals_each_street_one_second_apart(monkeypatch):
    session, events = runout_session(monkeypatch, 1)

    boards = session._deal_all_in_runout([])

    assert [event for event in events if event[0] in {"state", "sleep"}] == [
        ("state", 3),
        ("sleep", 1),
        ("state", 4),
        ("sleep", 1),
        ("state", 5),
    ]
    assert len(boards) == 1


def test_run_twice_completes_first_board_before_revealing_second(monkeypatch):
    session, events = runout_session(monkeypatch, 2)

    boards = session._deal_all_in_runout([])

    assert [event for event in events if event[0] in {"state", "sleep"}] == [
        ("state", 3),
        ("sleep", 1),
        ("state", 4),
        ("sleep", 1),
        ("state", 5),
        ("sleep", 1),
        ("state", 3),
        ("sleep", 1),
        ("state", 4),
        ("sleep", 1),
        ("state", 5),
        ("state", 5),
    ]
    assert session.runout_snapshots == [
        None,
        None,
        None,
        [5, 3],
        [5, 4],
        [5, 5],
        [5, 5],
    ]
    assert len(boards) == 2


def test_turn_all_in_run_twice_reveals_rivers_one_at_a_time(monkeypatch):
    turn_board = [c("2", "clubs"), c("3", "clubs"), c("4", "clubs"), c("5", "clubs")]
    session, events = runout_session(monkeypatch, 2, turn_board)

    boards = session._deal_all_in_runout([])

    assert [event for event in events if event[0] in {"state", "sleep"}] == [
        ("state", 5),
        ("sleep", 1),
        ("state", 5),
        ("state", 5),
    ]
    assert session.runout_snapshots == [
        None,
        [5, 5],
        [5, 5],
    ]
    assert len(boards) == 2
