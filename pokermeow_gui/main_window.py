from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .controller import ClientController
from .views import PokerStack, compact_card_text


class ControllerBridge(QObject):
    event_received = Signal(str, object)


class MainWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self.setWindowTitle("PokerMeow")
        self.resize(1180, 760)
        self.controller = controller or ClientController()
        self.pages = PokerStack()
        self.setCentralWidget(self.pages)
        self.bridge = ControllerBridge()
        self._leaving_after_bust = False
        self._rebuy_dialog = None
        self.bridge.event_received.connect(self._handle_event)
        self.controller.subscribe("*", self.bridge.event_received.emit)

        self.pages.menu.connect_requested.connect(self._connect)
        self.pages.lobby.leave_requested.connect(self._leave)
        self.pages.table.leave_requested.connect(self._leave)
        self.pages.table.action_requested.connect(self._submit_action)
        self.statusBar().showMessage("Ready")

    def closeEvent(self, event):
        self.controller.disconnect()
        super().closeEvent(event)

    def _connect(self, options):
        try:
            self.controller.connect(**options)
        except (ConnectionError, OSError, RuntimeError, ValueError) as error:
            self.pages.menu.set_status(str(error))
            QMessageBox.warning(self, "Could not connect", str(error))

    def _leave(self):
        self.controller.disconnect()
        self.pages.table.reset_session()
        self.pages.setCurrentWidget(self.pages.menu)
        self.pages.menu.set_status("Disconnected.")

    def _submit_action(self, action, amount):
        try:
            self.controller.submit_action(action, amount)
        except (ConnectionError, ValueError) as error:
            QMessageBox.warning(self, "Action failed", str(error))

    def _handle_event(self, event, payload):
        if event == "status":
            self.statusBar().showMessage(str(payload))
            self.pages.menu.set_status(str(payload))
        elif event == "connected":
            self.pages.lobby.configure(self.controller.is_host)
            self.pages.lobby.set_status("Connected. Setting up the table…")
            self.pages.setCurrentWidget(self.pages.lobby)
        elif event == "lobby_entered":
            self.pages.lobby.configure(payload.get("is_host", False))
        elif event == "table_created":
            table_id = payload.get("table_id", "")
            self.pages.lobby.set_table_id(table_id)
            self.pages.table.set_table_context(table_id)
            self.pages.lobby.set_status(payload.get("message", "Table created."))
        elif event == "joined":
            self.pages.lobby.set_status(
                f"Joined as {payload.get('name', self.controller.username)}."
            )
        elif event == "table":
            self.pages.lobby.update_table(payload)
            self.pages.table.set_table_context(payload.get("table_id"))
        elif event == "lobby_status":
            self.pages.lobby.set_status(payload.get("message", "Waiting…"))
        elif event == "seat_required":
            self._choose_seat(payload)
        elif event == "state":
            state = payload.get("state", {})
            table = payload.get("table")
            self.pages.table.update_state(state, table, self.controller.username)
            self.pages.lobby.update_table(table)
            self.pages.setCurrentWidget(self.pages.table)
        elif event == "action_required":
            self.pages.table.set_legal_actions(payload)
        elif event == "action_sent":
            self.pages.table.clear_legal_actions()
        elif event == "message":
            if payload == "New hand started.":
                self.pages.table.start_new_hand()
            else:
                self.pages.table.append_history(payload)
            self.pages.table.append_chat(f"Table: {payload}")
        elif event == "disconnect_timer":
            text = (
                f"{payload.get('player')} reconnect timer: "
                f"{payload.get('seconds')}s"
            )
            self.pages.table.append_history(text)
        elif event == "showdown":
            self._show_showdown(payload)
        elif event == "rebuy_required":
            self._request_rebuy(payload)
        elif event == "rebought":
            self._leaving_after_bust = False
            message = payload.get("message", "Rebuy successful.")
            self.pages.table.append_history(message)
            self.statusBar().showMessage(message, 5000)
        elif event == "allocator_required":
            self._request_allocation(payload)
        elif event == "name_required":
            self._request_new_name(str(payload))
        elif event == "table_id_required":
            self._request_table_id(str(payload))
        elif event == "error":
            self.pages.table.append_history(f"Error: {payload}")
            QMessageBox.warning(self, "PokerMeow", str(payload))
        elif event == "session_over":
            if self._rebuy_dialog is not None:
                self._rebuy_dialog.reject()
            if not self._leaving_after_bust:
                QMessageBox.information(self, "Session ended", str(payload))
            self._leaving_after_bust = False
            self._leave()
        elif event == "disconnected":
            if self._rebuy_dialog is not None:
                self._rebuy_dialog.reject()
            self.statusBar().showMessage(str(payload))
            self.pages.menu.set_status(str(payload))
            self.pages.setCurrentWidget(self.pages.menu)

    def _choose_seat(self, payload):
        seats = [str(seat) for seat in payload.get("available_seats", [])]
        if not seats:
            return
        selected, accepted = QInputDialog.getItem(
            self,
            "Choose a seat",
            "Available seat:",
            seats,
            0,
            False,
        )
        if accepted:
            self.controller.choose_seat(int(selected))

    def _request_new_name(self, message):
        name, accepted = QInputDialog.getText(
            self,
            "Choose another username",
            message,
            text=self.controller.username,
        )
        if accepted and name.strip():
            self.controller.submit_name(name)

    def _request_table_id(self, message):
        table_id, accepted = QInputDialog.getText(
            self,
            "Join table",
            message,
            text=self.controller.table_id,
        )
        if accepted and table_id.strip():
            self.controller.submit_table_id(table_id)

    def _request_rebuy(self, request):
        dialog = QDialog(self)
        dialog.setWindowTitle("Rebuy")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                request.get(
                    "message",
                    "You are out of chips. Rebuy to keep your seat.",
                )
            )
        )
        amount = QDoubleSpinBox()
        amount.setRange(0.01, 1_000_000_000)
        amount.setDecimals(2)
        amount.setValue(
            float(request.get("default_amount", self.controller.buy_in))
        )
        form = QFormLayout()
        form.addRow("Rebuy amount", amount)
        layout.addLayout(form)
        seconds = request.get("seconds")
        if seconds:
            timeout_label = QLabel(
                f"Your seat will be released after {seconds} seconds."
            )
            timeout_label.setObjectName("muted")
            layout.addWidget(timeout_label)
            QTimer.singleShot(
                max(1, int(seconds) - 1) * 1000,
                dialog.reject,
            )

        buttons = QHBoxLayout()
        rebuy_button = QPushButton("Rebuy")
        rebuy_button.setObjectName("primary")
        leave_button = QPushButton("Leave")
        buttons.addWidget(rebuy_button)
        buttons.addWidget(leave_button)
        layout.addLayout(buttons)
        rebuy_button.clicked.connect(dialog.accept)
        leave_button.clicked.connect(dialog.reject)

        self._rebuy_dialog = dialog
        result = dialog.exec()
        self._rebuy_dialog = None
        if not self.controller.connected:
            return
        if result == QDialog.DialogCode.Accepted:
            self.controller.submit_rebuy(amount.value())
        else:
            self._leaving_after_bust = True
            self.controller.submit_rebuy()

    def _show_showdown(self, result):
        winners = ", ".join(result.get("winners", [])) or "Unknown"
        hand_names = result.get("winner_hand_names", {})
        winner_details = ", ".join(
            f"{name} ({hand_names.get(name, result.get('hand_name', ''))})"
            for name in result.get("winners", [])
        )
        lines = ["", "SHOWDOWN"]
        hands = result.get("hands", [])
        self.pages.table.show_showdown_hands(hands)
        if hands:
            lines.append("Revealed hands:")
            for hand_info in hands:
                cards = " ".join(
                    compact_card_text(card)
                    for card in hand_info.get("hand", [])
                )
                rankings = hand_info.get("rankings")
                if rankings:
                    ranking = (
                        f"Top: {rankings.get('top', '—')}; "
                        f"Bottom: {rankings.get('bottom', '—')}; "
                        f"Strength: {rankings.get('hand_strength', '—')}; "
                        f"Total: {rankings.get('total', '—')} points"
                    )
                else:
                    ranking = hand_info.get("hand_name", "Unknown hand")
                lines.append(
                    f"  {hand_info.get('player', 'Player')}: "
                    f"{cards} \u2014 {ranking}"
                )
        else:
            lines.append("Cards not revealed (hand won uncontested).")

        winner_label = "Winner" if len(result.get("winners", [])) == 1 else "Winners"
        lines.append(f"{winner_label}: {winner_details or winners}")
        for name, amount in result.get("amount_won", {}).items():
            lines.append(f"Amount won by {name}: {amount}")
        lines.append("Next hand starts in 3 seconds.")
        self.pages.table.append_history("\n".join(lines))
        self.statusBar().showMessage("Showdown — next hand in 3 seconds", 3000)

    def _request_allocation(self, payload):
        dialog = QDialog(self)
        dialog.setWindowTitle("Allocator card allocation")
        layout = QVBoxLayout(dialog)
        hand = payload.get("hand", [])
        layout.addWidget(QLabel("Cards: " + ", ".join(
            f"{index}: {card}" for index, card in enumerate(hand, 1)
        )))
        form = QFormLayout()
        top = QLineEdit()
        bottom = QLineEdit()
        strength = QLineEdit()
        for field in (top, bottom, strength):
            field.setPlaceholderText("Two card numbers, e.g. 1 4")
        form.addRow("Top board cards", top)
        form.addRow("Bottom board cards", bottom)
        form.addRow("Hand strength cards", strength)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if not dialog.exec():
            return
        try:
            buckets = [
                [int(value) for value in field.text().replace(",", " ").split()]
                for field in (top, bottom, strength)
            ]
            flattened = [value for bucket in buckets for value in bucket]
            if any(len(bucket) != 2 for bucket in buckets):
                raise ValueError("Choose exactly two cards for each row.")
            if sorted(flattened) != list(range(1, 7)):
                raise ValueError("Use every card number from 1 to 6 exactly once.")
            self.controller.submit_allocator_allocation(*buckets)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid allocation", str(error))
