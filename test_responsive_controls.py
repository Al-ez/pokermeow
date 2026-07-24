import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokermeow_gui.views import (
    MainMenuView,
    ResponsiveChoiceButton,
    ResponsiveDoubleSpinBox,
)


def test_compact_controls_reduce_their_text_size_when_space_shrinks():
    app = QApplication.instance() or QApplication([])
    button = ResponsiveChoiceButton("30")
    spin_box = ResponsiveDoubleSpinBox()
    spin_box.setRange(0, 999999)
    spin_box.setValue(123456)

    button.resize(28, 15)
    spin_box.resize(55, 16)
    button.show()
    spin_box.show()
    app.processEvents()

    assert 9 <= button._responsive_text_size < 14
    assert 9 <= spin_box._responsive_text_size < 14


def test_aof_multiplier_and_numeric_inputs_use_responsive_controls():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.game.setCurrentIndex(menu.game.findData("aof"))
    menu.resize(1020, 650)
    menu.show()
    app.processEvents()

    assert all(
        isinstance(button, ResponsiveChoiceButton)
        for button in menu.aof_multiplier_buttons.values()
    )
    assert isinstance(menu.aof_ante, ResponsiveDoubleSpinBox)


def test_pof_creation_exposes_hole_cards_ante_and_existing_buy_in():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.game.setCurrentIndex(menu.game.findData("pof"))
    app.processEvents()

    assert set(menu.pof_hole_card_buttons) == {4, 5, 6}
    assert all(
        isinstance(button, ResponsiveChoiceButton)
        for button in menu.pof_hole_card_buttons.values()
    )
    assert menu.pof_hole_cards_group.checkedId() == 6
    assert menu.pof_hole_cards.isVisibleTo(menu.host_box)
    assert menu.pof_ante.isVisibleTo(menu.host_box)
    assert menu.buy_in.isVisibleTo(menu)
    assert not menu.aof_run_twice.isVisibleTo(menu.host_box)
