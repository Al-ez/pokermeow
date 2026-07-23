from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .views import card_display_color, compact_card_text


class AOFDiscardDialog(QDialog):
    discarded = Signal(int)

    def __init__(self, cards, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AOF discard")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose one card to discard before acting."))
        cards_layout = QHBoxLayout()
        self.card_buttons = []
        for index, card in enumerate(cards):
            button = QPushButton(compact_card_text(card))
            button.setToolTip(str(card))
            button.setFixedSize(72, 96)
            button.setStyleSheet(
                "background: white;"
                f"color: {card_display_color(card)};"
                "border: 2px solid #94a3b8; border-radius: 8px;"
                "font-size: 20px; font-weight: 800;"
            )
            button.clicked.connect(
                lambda checked=False, selected=index: self._discard(selected)
            )
            self.card_buttons.append(button)
            cards_layout.addWidget(button)
        layout.addLayout(cards_layout)
        self.status = QLabel("")
        layout.addWidget(self.status)

    def _discard(self, card_index):
        for button in self.card_buttons:
            button.setEnabled(False)
        self.status.setText("Discard submitted. Waiting for other players.")
        self.discarded.emit(card_index)

    def reject(self):
        # A discard is mandatory; the server closes the dialog after accepting it.
        return
