import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from pokermeow_gui.allocator_dialog import AllocatorDialog, BoardCard
from pokermeow_gui.views import CardFanWidget


def test_allocator_boards_render_as_cards_beside_allocation_slots():
    app = QApplication.instance() or QApplication([])
    dialog = AllocatorDialog(
        ["A♠", "K♠", "Q♥", "J♥", "10♣", "9♣"],
        top_board=["2♠", "3♠", "4♠"],
        bottom_board=["5♥", "6♥", "7♥"],
    )

    board_cards = dialog.findChildren(BoardCard)
    board_labels = dialog.findChildren(QLabel, "allocatorBoardLabel")

    assert len(board_cards) == 6
    assert [card.property("board") for card in board_cards].count("top") == 3
    assert [card.property("board") for card in board_cards].count("bottom") == 3
    assert len(board_labels) == 2
    assert not any(
        label.text().startswith(("Top board:", "Bottom board:"))
        for label in dialog.findChildren(QLabel)
    )

    dialog.close()
    app.processEvents()


def test_twelve_card_fan_uses_two_rows_of_six():
    app = QApplication.instance() or QApplication([])
    fan = CardFanWidget()
    fan.resize(180, 90)
    fan.set_cards(
        ["A♠", "K♠", "Q♠", "J♠", "10♠", "9♠",
         "8♥", "7♥", "6♥", "5♥", "4♥", "3♥"]
    )
    app.processEvents()

    assert len({label.y() for label in fan.card_labels}) == 2
    assert [label.y() for label in fan.card_labels[:6]] == [
        fan.card_labels[0].y()
    ] * 6
    assert [label.y() for label in fan.card_labels[6:]] == [
        fan.card_labels[6].y()
    ] * 6
    assert max(label.geometry().right() for label in fan.card_labels) < fan.width()

    fan.close()
