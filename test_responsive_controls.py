import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokermeow_gui.views import (
    MainMenuView,
    ResponsiveChoiceButton,
    ResponsiveDoubleSpinBox,
    ResponsiveSpinBox,
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


def test_plo_creation_exposes_cards_boards_and_big_blind():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.game.setCurrentIndex(menu.game.findData("plo"))
    app.processEvents()

    assert set(menu.plo_hole_card_buttons) == {4, 5, 6}
    assert set(menu.plo_board_buttons) == {1, 2}
    assert set(menu.plo_mode_buttons) == {"preflop", "bomb_pot"}
    assert menu.plo_hole_cards_group.checkedId() == 4
    assert menu.plo_boards_group.checkedId() == 1
    assert menu.plo_mode_group.checkedId() == 0
    assert menu.plo_hole_cards.isVisibleTo(menu.host_box)
    assert menu.plo_boards.isVisibleTo(menu.host_box)
    assert menu.plo_mode.isVisibleTo(menu.host_box)
    assert menu.big_blind.isVisibleTo(menu.host_box)
    assert menu.big_blind.value() == 2
    assert menu.seats.maximum() == 10
    assert not menu.plo_ante_bb.isVisibleTo(menu.host_box)

    menu.plo_mode_buttons["bomb_pot"].click()
    app.processEvents()

    assert menu.plo_ante_bb.isVisibleTo(menu.host_box)
    assert isinstance(menu.plo_ante_bb, ResponsiveSpinBox)


def test_pineapple_creation_exposes_ante_and_existing_buy_in():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.game.setCurrentIndex(menu.game.findData("pineapple"))
    app.processEvents()

    assert menu.pineapple_ante.isVisibleTo(menu.host_box)
    assert menu.buy_in.isVisibleTo(menu)
    assert not menu.big_blind.isVisibleTo(menu.host_box)
    assert menu.seats.maximum() == 10


def test_ultra_pineapple_creation_exposes_ante_and_seven_seat_cap():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.game.setCurrentIndex(menu.game.findData("ultra_pineapple"))
    app.processEvents()

    assert menu.ultra_pineapple_ante.isVisibleTo(menu.host_box)
    assert menu.buy_in.isVisibleTo(menu)
    assert not menu.big_blind.isVisibleTo(menu.host_box)
    assert menu.seats.maximum() == 7


def test_terminator_creation_exposes_its_bomb_pot_ante():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.game.setCurrentIndex(menu.game.findData("terminator"))
    app.processEvents()

    assert menu.terminator_ante.isVisibleTo(menu.host_box)
    assert not menu.big_blind.isVisibleTo(menu.host_box)
    assert menu.seats.maximum() == 7


def test_home_screen_has_top_right_settings_gear():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    requested = []
    menu.settings_requested.connect(lambda: requested.append(True))
    menu.resize(1180, 720)
    menu.show()
    app.processEvents()

    assert menu.settings_button.text() == "⚙"
    assert menu.settings_button.toolTip() == "Settings"
    assert menu.settings_button.x() > menu.width() / 2
    menu.settings_button.click()
    assert requested == [True]


def test_all_game_forms_keep_nlh_viewport_and_overflow_scrolls():
    app = QApplication.instance() or QApplication([])
    menu = MainMenuView()
    menu.resize(1020, 650)
    menu.show()
    app.processEvents()
    nlh_height = menu.host_scroll.height()

    menu.game.setCurrentIndex(menu.game.findData("plo"))
    menu.plo_mode_buttons["bomb_pot"].click()
    app.processEvents()

    assert menu.host_scroll.height() == nlh_height
    assert menu.host_scroll.verticalScrollBar().maximum() > 0
    assert menu.host_scroll.horizontalScrollBar().maximum() == 0
