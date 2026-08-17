import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokermeow_gui.views import PokerTableDisplay


def render_board_html(state):
    QApplication.instance() or QApplication([])
    return PokerTableDisplay()._community_cards_html(state)


def test_double_board_labels_and_cards_share_table_rows():
    html = render_board_html(
        {
            "top_board": ["A of spades"],
            "bottom_board": ["K of hearts"],
        }
    )

    assert "<b>Top:</b></td><td><table" in html
    assert "<b>Bottom:</b></td><td><table" in html


def test_terminator_marker_is_right_of_only_the_terminated_board():
    html = render_board_html(
        {
            "top_board": ["A of spades"],
            "bottom_board": ["K of hearts"],
            "terminated_board": "top",
            "terminated_ranks": ["A"],
        }
    )
    marker_position = html.index(">X</td>")
    assert html.count(">X</td>") == 1
    assert html.index("<b>Top:</b>") < marker_position
    assert marker_position < html.index("<b>Bottom:</b>")
    assert "background:#000000" in html
    assert "font-family:Arial Black" in html


def test_terminator_count_panel_lists_rank_totals():
    app = QApplication.instance() or QApplication([])
    display = PokerTableDisplay()

    display._update_termination_counts(
        {
            "terminated_board": "top",
            "terminated_card_counts": {"A": 3, "J": 4, "8": 2},
        }
    )
    app.processEvents()

    assert not display.termination_count_label.isHidden()
    assert "Terminated cards" in display.termination_count_label.text()
    assert "A</b> x3" in display.termination_count_label.text()
    assert "J</b> x4" in display.termination_count_label.text()
    assert "8</b> x2" in display.termination_count_label.text()


def test_esg_deck_size_is_shown_and_hidden_for_other_games():
    app = QApplication.instance() or QApplication([])
    display = PokerTableDisplay(show_game_details=True)
    table = {"seats": []}

    display.update_game({"pot": 3, "deck_size": 34, "players": {}}, table, "Alice")
    app.processEvents()
    assert display.deck_size_label.text() == "Deck: 34 cards"
    assert not display.deck_size_label.isHidden()

    display.update_game({"pot": 3, "players": {}}, table, "Alice")
    assert display.deck_size_label.isHidden()


def test_special_showdown_announcement_names_the_winner_and_hand():
    app = QApplication.instance() or QApplication([])
    display = PokerTableDisplay(show_game_details=True)
    display.show_winner_announcement(
        {
            "winners": ["Alice"],
            "winner_hand_names": {"Alice": "full house"},
            "hands": [],
        }
    )
    app.processEvents()
    assert display.winning_hand_label.text() == "Alice wins with Full House"


def test_esg_stage_announcement_names_each_category_winner():
    app = QApplication.instance() or QApplication([])
    display = PokerTableDisplay(show_game_details=True)
    display.spotlight_allocator_stage(
        {
            "players": {"Alice": {"label": "full house", "cards": []}},
            "winners": [{"player": "Alice"}],
        },
        "Hand Strength",
        True,
    )
    app.processEvents()
    assert "Alice wins with Full House" in display.winning_hand_label.text()
