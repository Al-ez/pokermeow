import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from config import WINDOWED_SIZE
from pokermeow_gui.main_window import MainWindow


def test_windowed_mode_keeps_fixed_testing_dimensions():
    QApplication.instance() or QApplication([])
    window = MainWindow(fullscreen=False)
    width, height = WINDOWED_SIZE

    assert window.minimumWidth() == window.maximumWidth() == width
    assert window.minimumHeight() == window.maximumHeight() == height


def test_fullscreen_mode_allows_responsive_monitor_dimensions():
    QApplication.instance() or QApplication([])
    window = MainWindow(fullscreen=True)

    assert window.minimumWidth() == 900
    assert window.minimumHeight() == 600
    assert window.maximumWidth() == QWidget().maximumWidth()
    assert window.maximumHeight() == QWidget().maximumHeight()


def test_runtime_setting_switches_between_display_modes():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(fullscreen=False)
    window.show()
    window.set_fullscreen(True)
    app.processEvents()
    assert window.isFullScreen()
    assert window.maximumWidth() == QWidget().maximumWidth()

    window.set_fullscreen(False)
    app.processEvents()
    assert not window.isFullScreen()
    assert window.width() == WINDOWED_SIZE[0]


def test_settings_dialog_has_toggle_quit_and_top_right_close_buttons():
    QApplication.instance() or QApplication([])
    window = MainWindow(fullscreen=False)
    dialog = window._create_settings_dialog()

    toggle = dialog.findChild(QPushButton, "fullscreenToggle")
    quit_button = dialog.findChild(QPushButton, "quitGameButton")
    close_button = dialog.findChild(QPushButton, "settingsCloseButton")
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert toggle is not None and toggle.text() == "Off"
    assert quit_button is not None and quit_button.text() == "Quit Game"
    assert close_button is not None and close_button.text() == "X"

    dialog.show()
    close_button.click()
    assert not dialog.isVisible()
