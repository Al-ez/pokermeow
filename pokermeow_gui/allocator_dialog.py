from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .views import card_display_color, compact_card_html


CARD_MIME = "application/x-pokermeow-card-index"


class AllocationCard(QLabel):
    clicked = Signal(int)

    def __init__(self, index, card, parent=None):
        super().__init__(compact_card_html(card), parent)
        self.index = index
        self.setToolTip(str(card))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedSize(64, 88)
        self.setStyleSheet(self._style(False))

    def _style(self, selected):
        color = card_display_color(self.toolTip())
        border = "3px solid #2563eb" if selected else "1px solid #94a3b8"
        return (
            f"background: white; color: {color}; border: {border}; "
            "border-radius: 8px; font-size: 22px; font-weight: 700;"
        )

    def set_selected(self, selected):
        self.setStyleSheet(self._style(selected))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(CARD_MIME, str(self.index).encode("ascii"))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
        super().mouseMoveEvent(event)


class AllocationSlot(QLabel):
    card_dropped = Signal(object, int)
    clicked = Signal(object)

    def __init__(self, bucket, position, parent=None):
        super().__init__(parent)
        self.bucket = bucket
        self.position = position
        self.card_index = None
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(70, 94)
        self.refresh(None, None)

    def refresh(self, index, card):
        self.card_index = index
        self.setText(compact_card_html(card) if card else "+")
        if card:
            color = card_display_color(card)
        else:
            color = "#64748b"
        self.setStyleSheet(
            f"background: #f8fafc; color: {color}; border: 2px dashed #94a3b8; "
            "border-radius: 8px; font-size: 21px; font-weight: 700;"
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CARD_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        index = int(bytes(event.mimeData().data(CARD_MIME)).decode("ascii"))
        self.card_dropped.emit(self, index)
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)


class BoardCard(QLabel):
    def __init__(self, card, board, parent=None):
        super().__init__(compact_card_html(card), parent)
        self.setObjectName("allocatorBoardCard")
        self.setProperty("board", board)
        self.setToolTip(str(card))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(48, 66)
        self.setStyleSheet(
            "background: white; "
            f"color: {card_display_color(card)}; "
            "border: 1px solid #94a3b8; border-radius: 7px; "
            "font-size: 18px; font-weight: 700;"
        )


class AllocatorDialog(QDialog):
    submitted = Signal(list, list, list)
    ready_cancelled = Signal()

    BUCKETS = (
        ("top", "Top board"),
        ("bottom", "Bottom board"),
        ("hand", "Hand strength"),
    )

    def __init__(self, cards, top_board=None, bottom_board=None, parent=None):
        super().__init__(parent)
        self.cards = list(cards)
        self.selected_index = None
        self.is_ready = False
        self.assignments = {name: [None, None] for name, _ in self.BUCKETS}
        self.card_widgets = {}
        self.slots = {}
        self.setWindowTitle("Card allocation")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setMinimumWidth(650)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Drag each card into a slot, or click a card and then an empty slot. "
            "Click an assigned card to return it."
        ))

        card_row = QGridLayout()
        for index, card in enumerate(self.cards, 1):
            widget = AllocationCard(index, card)
            widget.clicked.connect(self.select_card)
            self.card_widgets[index] = widget
            card_row.addWidget(widget, (index - 1) // 6, (index - 1) % 6)
        layout.addLayout(card_row)

        grid = QGridLayout()
        boards = {
            "top": list(top_board or []),
            "bottom": list(bottom_board or []),
        }
        for row, (bucket, title) in enumerate(self.BUCKETS):
            grid.addWidget(QLabel(title), row, 0)
            for position in range(2):
                slot = AllocationSlot(bucket, position)
                slot.card_dropped.connect(self.assign_card)
                slot.clicked.connect(self.slot_clicked)
                self.slots[(bucket, position)] = slot
                grid.addWidget(slot, row, position + 1)
            board = boards.get(bucket, [])
            if board:
                board_label = QLabel("Board")
                board_label.setObjectName("allocatorBoardLabel")
                grid.addWidget(board_label, row, 3)
                for card_position, card in enumerate(board):
                    grid.addWidget(
                        BoardCard(card, bucket),
                        row,
                        card_position + 4,
                    )
        layout.addLayout(grid)

        self.status = QLabel("Choose six cards for the three scoring slots, then click Ready.")
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.confirm_button = QPushButton("Ready")
        self.confirm_button.clicked.connect(self.toggle_ready)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    def select_card(self, index):
        self.selected_index = index
        for card_index, widget in self.card_widgets.items():
            widget.set_selected(card_index == index)

    def slot_clicked(self, slot):
        if slot.card_index is not None:
            self.assignments[slot.bucket][slot.position] = None
            self._refresh()
        elif self.selected_index is not None:
            self.assign_card(slot, self.selected_index)

    def assign_card(self, slot, index):
        for values in self.assignments.values():
            for position, current in enumerate(values):
                if current == index:
                    values[position] = None
        displaced = self.assignments[slot.bucket][slot.position]
        self.assignments[slot.bucket][slot.position] = index
        self.selected_index = displaced
        self._refresh()

    def _refresh(self):
        used = {index for values in self.assignments.values() for index in values if index}
        for (bucket, position), slot in self.slots.items():
            index = self.assignments[bucket][position]
            slot.refresh(index, self.cards[index - 1] if index else None)
        for index, widget in self.card_widgets.items():
            widget.setVisible(index not in used)
            widget.set_selected(index == self.selected_index)

    def toggle_ready(self):
        if self.is_ready:
            self.is_ready = False
            self.ready_cancelled.emit()
            self.confirm_button.setText("Ready")
            self.status.setText("Ready cancelled. You can change your allocation.")
            self._set_editor_enabled(True)
            return

        buckets = [self.assignments[name] for name, _ in self.BUCKETS]
        flattened = [index for bucket in buckets for index in bucket]
        if any(index is None for index in flattened):
            QMessageBox.warning(self, "Invalid allocation", "Place one card in every slot.")
            return
        if len(set(flattened)) != 6:
            QMessageBox.warning(self, "Invalid allocation", "Use six different cards.")
            return
        self.submitted.emit(*[list(bucket) for bucket in buckets])
        self.is_ready = True
        self.confirm_button.setText("Cancel ready")
        self.status.setText("Ready. Waiting for every other player to be ready.")
        self._set_editor_enabled(False)

    def _set_editor_enabled(self, enabled):
        for widget in self.card_widgets.values():
            widget.setEnabled(enabled)
        for slot in self.slots.values():
            slot.setEnabled(enabled)

    def lock(self):
        self.status.setText("All players are ready. Allocation locked.")
        self.accept()
