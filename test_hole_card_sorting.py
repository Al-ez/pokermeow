import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokermeow_gui.views import TableView, sort_hole_cards


def test_strength_sort_uses_descending_rank_then_requested_suit_order():
    cards = [
        "K of spades",
        "A of hearts",
        "K of diamonds",
        "Q of clubs",
    ]

    assert sort_hole_cards(cards, "strength") == [
        "A of hearts",
        "K of diamonds",
        "K of spades",
        "Q of clubs",
    ]


def test_suit_sort_groups_diamonds_clubs_hearts_spades_and_sorts_each_group():
    cards = [
        "2 of spades",
        "A of spades",
        "K of diamonds",
        "Q of clubs",
        "10 of spades",
        "A of diamonds",
    ]

    assert sort_hole_cards(cards, "suit") == [
        "A of diamonds",
        "K of diamonds",
        "Q of clubs",
        "A of spades",
        "10 of spades",
        "2 of spades",
    ]


def test_sort_controls_only_show_for_six_or_more_visible_hole_cards():
    app = QApplication.instance() or QApplication([])
    view = TableView()
    table = {"table_id": "AB12", "game": "POF", "seats": []}

    view.show()
    view.update_state(
        {"players": {"Alice": {"hand": ["A of spades"] * 5}}},
        table,
        "Alice",
    )
    app.processEvents()
    assert not view.card_sort_controls.isVisible()

    hand = [
        "2 of spades",
        "A of spades",
        "K of diamonds",
        "Q of clubs",
        "10 of spades",
        "A of diamonds",
    ]
    state = {"players": {"Alice": {"hand": hand}}}
    view.update_state(state, table, "Alice")
    app.processEvents()
    assert view.card_sort_controls.isVisible()

    view.card_sort_buttons["suit"].click()
    app.processEvents()
    displayed_cards = [
        label.toolTip()
        for label in view.table_display.action_widgets[1].cards_label.card_labels
    ]
    assert displayed_cards == sort_hole_cards(hand, "suit")
    assert state["players"]["Alice"]["hand"] == hand
