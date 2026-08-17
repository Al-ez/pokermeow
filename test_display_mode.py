import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

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
