import threading
from decimal import Decimal
from types import SimpleNamespace

from allocator import AllocatorGame
from server import PokerTableSession


class FakeClient:
    def __init__(self, name):
        self.name = name
        self.buy_in = Decimal("1000")
        self.connected = True
        self.messages = []

    def send(self, message):
        self.messages.append(message)


def make_session(shutdown_event=None):
    return PokerTableSession(
        table_id="TEST",
        game_class=AllocatorGame,
        game_name="Allocator",
        small_blind=Decimal("1"),
        big_blind=Decimal("2"),
        max_seats=2,
        bomb_pot_ante=1,
        shutdown_event=shutdown_event,
    )


def test_table_status_is_broadcast_to_host_when_second_player_sits():
    session = make_session()
    alez = FakeClient("Alez")
    bob = FakeClient("Bob")
    session.all_clients.extend([alez, bob])
    session.table.reserve_or_seat_client(alez, 1)
    session.table.reserve_or_seat_client(bob, 2)

    session._broadcast_table_status()

    host_table = alez.messages[-1]["table"]
    assert host_table["seats"][1]["player"] == "Bob"


def test_table_loop_starts_when_two_players_are_seated():
    shutdown = threading.Event()
    session = make_session(shutdown)
    alez = FakeClient("Alez")
    bob = FakeClient("Bob")
    session.table.reserve_or_seat_client(alez, 1)
    session.table.reserve_or_seat_client(bob, 2)
    started = threading.Event()

    def play_one_hand():
        started.set()
        shutdown.set()

    session._poll_control_messages = lambda clients, timeout=0: None
    session._play_hand = play_one_hand
    thread = threading.Thread(target=session.run)
    thread.start()
    thread.join(timeout=2)

    assert started.is_set()
    assert not thread.is_alive()


def test_allocator_showdown_timing_distinguishes_uncontested_pots():
    session = make_session()

    assert session._showdown_display_seconds(
        SimpleNamespace(hand_name="uncontested")
    ) == 2
    assert session._showdown_display_seconds(
        SimpleNamespace(hand_name="allocator score")
    ) == 15


def test_showdown_spotlight_includes_every_player_tied_for_strongest_hand():
    board = ["A♠", "K♥", "Q♣"]
    scores = {
        "Alez": (4, [14], board + ["J♦", "10♠"], "straight"),
        "Bob": (4, [14], board + ["J♣", "10♥"], "straight"),
        "Cara": (1, [9], board + ["9♦", "2♠"], "one pair"),
    }

    spotlight = PokerTableSession._spotlight_cards_for_scores(scores)

    assert spotlight == board + ["J♦", "10♠", "J♣", "10♥"]


if __name__ == "__main__":
    test_table_status_is_broadcast_to_host_when_second_player_sits()
    test_table_loop_starts_when_two_players_are_seated()
    test_allocator_showdown_timing_distinguishes_uncontested_pots()
    test_showdown_spotlight_includes_every_player_tied_for_strongest_hand()
    print("4 table session tests passed.")
