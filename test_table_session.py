import threading
from decimal import Decimal
from types import SimpleNamespace

from allocator import AllocatorGame
from aof import AOFGame
from server import PokerTableSession
from pof import PotOrFoldGame


class FakeClient:
    def __init__(self, name):
        self.name = name
        self.buy_in = Decimal("1000")
        self.connected = True
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class RespondingClient(FakeClient):
    def __init__(self, name, responses):
        super().__init__(name)
        self.responses = list(responses)

    def recv(self):
        return self.responses.pop(0) if self.responses else None


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


def test_chat_is_broadcast_and_only_the_latest_30_messages_are_stored():
    session = make_session()
    alez = FakeClient("Alez")
    bob = FakeClient("Bob")
    session.all_clients.extend([alez, bob])

    for number in range(31):
        session._handle_chat_message(
            alez,
            {"type": "chat", "message": f"Message {number + 1}"},
        )

    assert len(session.chat_messages) == 30
    assert session.chat_messages[0] == {
        "player": "Alez",
        "message": "Message 2",
    }
    assert bob.messages[-1] == {
        "type": "chat",
        "player": "Alez",
        "message": "Message 31",
    }

    session._send_chat_history(bob)
    history = bob.messages[-1]
    assert history["type"] == "chat_history"
    assert len(history["messages"]) == 30
    assert history["messages"][0]["message"] == "Message 2"


def test_aof_discards_are_collected_from_players_independently():
    session = PokerTableSession(
        table_id="AOF1",
        game_class=AOFGame,
        game_name="AOF",
        small_blind=Decimal("1"),
        big_blind=Decimal("2"),
        max_seats=2,
        aof_ante=Decimal("3"),
        aof_multiplier=10,
    )
    alice = RespondingClient(
        "Alice",
        [{"type": "aof_discard", "card_index": 0}],
    )
    bob = RespondingClient(
        "Bob",
        [{"type": "aof_discard", "card_index": 2}],
    )
    session.table.reserve_or_seat_client(alice, 1)
    session.table.reserve_or_seat_client(bob, 2)
    session.game = AOFGame(
        {"Alice": 100, "Bob": 100},
        ante=3,
        multiplier=10,
        shuffle=False,
    )
    session.game.start_hand()

    session._request_aof_discards([alice, bob])

    assert session.game.discarded_players == {"Alice", "Bob"}
    assert all(len(player.hand) == 2 for player in session.game.players)
    assert any(
        message.get("type") == "request_aof_discard"
        for message in alice.messages
    )
    assert any(message.get("type") == "aof_discarded" for message in bob.messages)
    assert any(
        message == {
            "type": "message",
            "message": "Alice has discarded a card.",
        }
        for message in bob.messages
    )
    assert any(
        message.get("type") == "state"
        and message["state"]["players"]["Alice"]["hand_size"] == 2
        for message in bob.messages
    )


def test_aof_run_twice_is_disabled_by_default():
    session = PokerTableSession(
        table_id="AOF1",
        game_class=AOFGame,
        game_name="AOF",
        small_blind=Decimal("1"),
        big_blind=Decimal("2"),
        max_seats=2,
        aof_ante=Decimal("3"),
        aof_multiplier=10,
    )
    session.game = AOFGame(
        {"Alice": 100, "Bob": 100},
        ante=3,
        multiplier=10,
        shuffle=False,
    )
    session.game.start_hand()

    assert session._request_run_it_vote([]) == 1


def test_pof_never_offers_run_it_twice():
    session = PokerTableSession(
        table_id="POF1",
        game_class=PotOrFoldGame,
        game_name="Pot or Fold",
        small_blind=Decimal("1"),
        big_blind=Decimal("2"),
        max_seats=2,
        pof_ante=Decimal("5"),
        pof_hole_cards=4,
    )
    session.game = PotOrFoldGame(
        {"Alice": 100, "Bob": 100},
        ante=5,
        hole_cards=4,
        shuffle=False,
    )
    session.game.start_hand()
    session.game.deal_flop()

    assert session._request_run_it_vote([]) == 1


def test_pof_pot_and_call_runs_to_exactly_five_cards_and_showdown():
    session = PokerTableSession(
        table_id="POF1",
        game_class=PotOrFoldGame,
        game_name="Pot or Fold",
        small_blind=Decimal("1"),
        big_blind=Decimal("2"),
        max_seats=2,
        pof_ante=Decimal("5"),
        pof_hole_cards=4,
    )
    alice = FakeClient("Alice")
    bob = FakeClient("Bob")
    alice.leave_after_hand = False
    bob.leave_after_hand = False
    session.table.reserve_or_seat_client(alice, 1)
    session.table.reserve_or_seat_client(bob, 2)

    betting_rounds = []
    showdowns = []

    def play_pof_betting_round(clients):
        betting_rounds.append(len(session.game.board))
        assert betting_rounds == [3]
        opener = session.game.players[session.game.action_index]
        session.game.act(opener.name, "pot")
        caller = session.game.players[session.game.action_index]
        session.game.act(caller.name, "call")

    def deal_single_runout(clients):
        session.game.deal_turn()
        session.game.deal_river()
        return [list(session.game.board)]

    session._broadcast_hand_message = lambda clients, message: None
    session._send_states_to = lambda clients: None
    session._run_betting_round = play_pof_betting_round
    session._deal_all_in_runout = deal_single_runout
    session._broadcast_to = lambda clients, message: showdowns.append(message)
    session._wait_for_showdown_display = lambda clients, duration: None
    session._activate_reserved_and_offer_waiting_list = lambda: None

    session._play_hand()

    assert betting_rounds == [3]
    assert len(session.game.board) == 5
    assert any(message.get("type") == "showdown" for message in showdowns)


def test_displayed_payout_is_the_full_amount_returned_from_the_pot():
    result = SimpleNamespace(amount_won={"Alice": Decimal("500")})

    assert PokerTableSession._displayed_payouts(result) == {
        "Alice": Decimal("500"),
    }


if __name__ == "__main__":
    test_table_status_is_broadcast_to_host_when_second_player_sits()
    test_table_loop_starts_when_two_players_are_seated()
    test_allocator_showdown_timing_distinguishes_uncontested_pots()
    test_showdown_spotlight_includes_every_player_tied_for_strongest_hand()
    test_chat_is_broadcast_and_only_the_latest_30_messages_are_stored()
    test_aof_discards_are_collected_from_players_independently()
    test_aof_run_twice_is_disabled_by_default()
    test_displayed_payout_is_the_full_amount_returned_from_the_pot()
    print("8 table session tests passed.")
