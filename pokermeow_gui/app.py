import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


STYLE = """
QWidget {
    background: #101827;
    color: #e5e7eb;
    font-size: 14px;
}
QGroupBox {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background: #182235;
    border: 1px solid #3b4a63;
    border-radius: 5px;
    padding: 7px;
    selection-background-color: #2563eb;
}
QPushButton {
    background: #263449;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton:hover { background: #334155; }
QPushButton:disabled { color: #64748b; background: #172033; }
QPushButton:checked {
    background: #2563eb;
    color: white;
    border-color: #3b82f6;
}
QPushButton#primary, QLabel#turnActive {
    background: #2563eb;
    color: white;
}
QLabel#title { font-size: 34px; font-weight: 800; color: #f8fafc; }
QLabel#sectionTitle { font-size: 22px; font-weight: 700; }
QLabel#subheading { font-size: 15px; font-weight: 600; }
QLabel#muted { color: #94a3b8; }
QLabel#pill {
    background: #1e3a5f;
    border-radius: 7px;
    padding: 7px 12px;
}
QFrame#pokerFelt {
    background: #064e3b;
    border: 8px solid #78350f;
    border-radius: 28px;
}
QLabel#feltPot {
    background: #052e2b;
    color: #fef3c7;
    border: 1px solid #f59e0b;
    border-radius: 14px;
    padding: 8px 16px;
    font-size: 18px;
    font-weight: 800;
}
QLabel#feltBoard {
    background: transparent;
    color: #f8fafc;
    border: none;
    padding: 0;
    font-size: 20px;
}
QFrame#pokerSeat {
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 14px;
}
QFrame#pokerSeat[occupied="true"] {
    background: #f8fafc;
    border: 1px solid #38bdf8;
}
QFrame#pokerSeat[hero="true"] {
    background: #f8fafc;
    border: 1px solid #38bdf8;
}
QFrame#pokerSeat[pickable="true"] {
    border: 2px solid #facc15;
    background: #fef9c3;
}
QLabel#seatPlayer {
    background: transparent;
    border: none;
    color: #111827;
    font-weight: 800;
    font-size: 13px;
}
QLabel#seatStack {
    background: transparent;
    border: none;
    color: #334155;
    font-size: 11px;
}
QWidget#tableAction {
    background: transparent;
    border: none;
}
QLabel#tableActionTop {
    color: #fde68a;
    font-weight: 800;
    font-size: 16px;
}
QLabel#seatHand {
    color: #93c5fd;
    font-size: 11px;
}
QLabel#dealerButton {
    background: #f8fafc;
    color: #111827;
    border-radius: 10px;
    min-width: 22px;
    min-height: 22px;
    max-width: 22px;
    font-weight: 900;
}
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PokerMeow")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
