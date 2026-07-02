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
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QTreeWidget {
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
QHeaderView::section {
    background: #263449;
    color: #e5e7eb;
    padding: 7px;
    border: none;
}
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PokerMeow")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
