import os
import time
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from nlh import NoLimitHoldemGame
from pokermeow_gui.views import MainMenuView, PokerTableDisplay
from server import PokerTableSession


class FakeClient:
    def __init__(self, name, responses=None):
        self.name = name
        self.buy_in = Decimal("1000")
        self.connected = True
        self.leave_after_hand = False
        self.messages = []
        self.responses = list(responses or [])

    def send(self, message):
        self.messages.append(message)

    def recv(self, stop_event=None):
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, tuple):
                delay, response = response
                time.sleep(delay)
            return response
        if stop_event is not None:
            stop_event.wait(timeout=2)
        return None


def make_session():
    session = PokerTableSession(
        table_id="ORB1",
        game_class=NoLimitHoldemGame,
        game_name="No-Limit Texas Hold'em",
        small_blind=1,
        big_blind=2,
        max_seats=4,
        orbital_special=True,
    )
    clients = [FakeClient(name) for name in ("A", "B", "C", "D")]
    for seat, client in enumerate(clients, 1):
        session.table.reserve_or_seat_client(client, seat)
    return session, clients


def test_orbital_button_starts_one_seat_behind_dealer_and_is_public():
    session, _clients = make_session()
    session._ensure_special_button()

    assert session._scheduled_dealer_name() == "A"
    assert session.special_button_seat == 4
    assert session._table_status()["special_button_player"] == "D"


def test_orbital_configuration_enforces_game_and_deck_seat_caps():
    session, _clients = make_session()
    config = session._normalize_orbital_config(
        {
            "game": "plo",
            "max_players": 10,
            "big_blind": 2,
            "ante": 10,
            "hole_cards": 6,
            "boards": 2,
            "mode": "preflop",
        },
        10,
    )

    assert config["max_players"] == 6


def test_orbital_hole_cards_are_derived_from_the_selected_variant():
    session, _clients = make_session()
    expected = {
        "nlh": 2,
        "aof": 3,
        "pineapple": 3,
        "ultra_pineapple": 5,
        "terminator": 6,
        "allocator": 6,
        "helicopter": 6,
        "esg": 6,
    }
    for game, hole_cards in expected.items():
        config = session._normalize_orbital_config(
            {
                "game": game,
                "max_players": 4,
                "big_blind": 2,
                "ante": 10,
                # Deliberately wrong: fixed variants must ignore this value.
                "hole_cards": 4,
                "boards": 1,
                "mode": "preflop",
            },
            4,
        )
        assert config["hole_cards"] == hole_cards


def test_invitation_config_only_contains_fields_relevant_to_esg():
    session, _clients = make_session()
    config = session._normalize_orbital_config(
        {
            "game": "esg",
            "max_players": 4,
            "big_blind": 2,
            "ante": 10,
            "hole_cards": 4,
            "boards": 1,
            "mode": "preflop",
            "multiplier": 10,
        },
        4,
    )

    assert session._orbital_public_config(config) == {
        "game": "ESG (Extremely Stupid Game)",
        "max_players": 4,
        "big_blind": Decimal("2"),
        "hole_cards": 6,
    }


def test_invitation_config_uses_variant_specific_fields():
    session, _clients = make_session()
    aof = session._normalize_orbital_config(
        {
            "game": "aof",
            "max_players": 4,
            "big_blind": 2,
            "ante": 3,
            "hole_cards": 6,
            "boards": 2,
            "mode": "preflop",
            "multiplier": 20,
            "allow_run_twice": True,
        },
        4,
    )
    public = session._orbital_public_config(aof)
    assert set(public) == {
        "game", "max_players", "hole_cards", "ante",
        "multiplier", "allow_run_twice",
    }
    assert "big_blind" not in public
    assert "boards" not in public


def test_creation_field_only_appears_for_nlh_and_plo():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.show()
    for game in ("nlh", "plo"):
        menu.game.setCurrentIndex(menu.game.findData(game))
        app.processEvents()
        assert menu.orbital_special.isVisibleTo(menu.host_box)
    menu.game.setCurrentIndex(menu.game.findData("esg"))
    app.processEvents()
    assert not menu.orbital_special.isVisibleTo(menu.host_box)


def test_sg_badge_follows_special_button_player():
    app = QApplication.instance() or QApplication([])
    display = PokerTableDisplay(show_game_details=True)
    display.show()
    table = {
        "special_button_player": "Bob",
        "seats": [
            {"seat": 1, "status": "seated", "player": "Alice", "stack": 100},
            {"seat": 2, "status": "seated", "player": "Bob", "stack": 100},
        ],
    }
    state = {
        "dealer": "Alice",
        "players": {"Alice": {"stack": 100}, "Bob": {"stack": 100}},
    }
    display.update_game(state, table, "Alice")
    app.processEvents()

    assert display.dealer_widgets[1].isVisible()
    assert display.special_game_widgets[2].isVisible()


def test_special_roster_honors_quota_and_auto_sits_out_remaining_players():
    session, clients = make_session()
    clients[0].responses.append(
        {
            "type": "orbital_special_selection",
            "config": {
                "game": "nlh",
                "max_players": 2,
                "big_blind": 2,
                "ante": 10,
                "hole_cards": 4,
                "boards": 1,
                "mode": "preflop",
            },
        }
    )
    clients[1].responses.append({"type": "orbital_special_vote", "play": True})
    played = []
    session._play_hand = lambda **kwargs: played.append(kwargs)

    session._run_orbital_special("A")

    assert [client.name for client in played[0]["seated_clients_override"]] == ["A", "B"]
    assert played[0]["dealer_name_override"] == "A"
    assert any(message["type"] == "orbital_special_full" for message in clients[2].messages)
    assert any(message["type"] == "orbital_special_full" for message in clients[3].messages)
    assert session.game_class is NoLimitHoldemGame


def test_concurrent_votes_admit_the_fastest_players_not_seat_order():
    session, clients = make_session()
    clients[0].responses.append(
        {
            "type": "orbital_special_selection",
            "config": {
                "game": "nlh",
                "max_players": 2,
                "big_blind": 2,
                "ante": 10,
                "hole_cards": 4,
                "boards": 1,
                "mode": "preflop",
            },
        }
    )
    clients[1].responses.append(
        (0.08, {"type": "orbital_special_vote", "play": True})
    )
    clients[2].responses.append(
        (0.01, {"type": "orbital_special_vote", "play": True})
    )
    played = []
    session._play_hand = lambda **kwargs: played.append(kwargs)

    session._run_orbital_special("A")

    assert [client.name for client in played[0]["seated_clients_override"]] == ["A", "C"]
    for client in clients[1:]:
        assert any(
            message["type"] == "request_orbital_special_vote"
            for message in client.messages
        )
    assert any(message["type"] == "orbital_special_full" for message in clients[1].messages)
    assert any(message["type"] == "orbital_special_full" for message in clients[3].messages)
