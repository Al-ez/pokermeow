from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
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

from config import WINDOWED_SIZE
from .controller import ClientController
from .allocator_dialog import AllocatorDialog
from .aof_dialog import AOFDiscardDialog
from .orbital_dialog import OrbitalInvitationDialog, OrbitalSelectionDialog
from .views import PokerStack


class ControllerBridge(QObject):
    event_received = Signal(str, object)


class MainWindow(QMainWindow):
    def __init__(self, controller=None, fullscreen=False):
        super().__init__()
        self.setWindowTitle("PokerMeow")
        self.fullscreen = bool(fullscreen)
        if self.fullscreen:
            self.setMinimumSize(900, 600)
        else:
            self.setFixedSize(*WINDOWED_SIZE)
        self.controller = controller or ClientController()
        self.pages = PokerStack()
        self.setCentralWidget(self.pages)
        self.bridge = ControllerBridge()
        self._leaving_after_bust = False
        self._leave_pending = False
        self._rebuy_dialog = None
        self._allocator_dialog = None
        self._aof_dialog = None
        self._orbital_dialog = None
        self._showdown_seconds = 0
        self._showdown_timer = QTimer(self)
        self._showdown_timer.setInterval(1000)
        self._showdown_timer.timeout.connect(self._tick_showdown_timer)
        self._run_it_timer = QTimer(self)
        self._run_it_timer.setSingleShot(True)
        self._run_it_timer.timeout.connect(self.pages.table.hide_run_it_prompt)
        self.bridge.event_received.connect(self._handle_event)
        self.controller.subscribe("*", self.bridge.event_received.emit)

        self.pages.menu.connect_requested.connect(self._connect)
        self.pages.menu.settings_requested.connect(self._open_settings)
        self.pages.lobby.leave_requested.connect(self._request_leave)
        self.pages.lobby.seat_selected.connect(self._select_seat)
        self.pages.table.leave_requested.connect(self._request_leave)
        self.pages.table.action_requested.connect(self._submit_action)
        self.pages.table.run_it_requested.connect(self._submit_run_it_vote)
        self.pages.table.chat_requested.connect(self._submit_chat)
        self.statusBar().showMessage("Ready")

    def _open_settings(self):
        self._create_settings_dialog().exec()

    def _create_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        layout = QVBoxLayout(dialog)
        title_row = QHBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("sectionTitle")
        close_button = QPushButton("X")
        close_button.setObjectName("settingsCloseButton")
        close_button.setToolTip("Close settings")
        close_button.setFixedSize(34, 34)
        close_button.clicked.connect(dialog.reject)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_button)
        layout.addLayout(title_row)

        fullscreen_row = QHBoxLayout()
        fullscreen_row.addWidget(QLabel("Fullscreen"))
        fullscreen_row.addStretch()
        fullscreen_toggle = QPushButton()
        fullscreen_toggle.setObjectName("fullscreenToggle")
        fullscreen_toggle.setCheckable(True)
        fullscreen_toggle.setChecked(self.isFullScreen() or self.fullscreen)
        self._update_fullscreen_toggle_text(fullscreen_toggle)
        fullscreen_toggle.clicked.connect(
            lambda checked: self._toggle_fullscreen_setting(
                fullscreen_toggle,
                checked,
            )
        )
        fullscreen_row.addWidget(fullscreen_toggle)
        layout.addLayout(fullscreen_row)

        quit_button = QPushButton("Quit Game")
        quit_button.setObjectName("quitGameButton")
        quit_button.setStyleSheet(
            "QPushButton { background: #991b1b; color: white; font-weight: 800; }"
        )
        quit_button.clicked.connect(lambda: self._confirm_quit(dialog))
        layout.addWidget(quit_button)
        dialog.setMinimumWidth(330)
        return dialog

    def _toggle_fullscreen_setting(self, button, fullscreen):
        self.set_fullscreen(fullscreen)
        QSettings("PokerMeow", "PokerMeow").setValue("fullscreen", fullscreen)
        self._update_fullscreen_toggle_text(button)

    @staticmethod
    def _update_fullscreen_toggle_text(button):
        button.setText("On" if button.isChecked() else "Off")

    def _confirm_quit(self, dialog):
        answer = QMessageBox.question(
            dialog,
            "Quit Game",
            "Are you sure you want to quit the game?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            dialog.accept()
            self.close()

    def set_fullscreen(self, fullscreen):
        self.fullscreen = bool(fullscreen)
        if self.fullscreen:
            self.setMinimumSize(900, 600)
            self.setMaximumSize(16777215, 16777215)
            self.showFullScreen()
        else:
            self.showNormal()
            self.setFixedSize(*WINDOWED_SIZE)

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
        if self._aof_dialog is not None:
            self._aof_dialog.accept()
            self._aof_dialog = None
        self.controller.disconnect()
        self._leave_pending = False
        self.pages.table.reset_session()
        self.pages.lobby.set_leave_pending(False)
        self.pages.setCurrentWidget(self.pages.menu)
        self.pages.menu.set_status("Disconnected.")

    def _request_leave(self):
        if not self.controller.connected:
            self._leave()
            return
        if self._leave_pending:
            self.statusBar().showMessage("Cancelling leave request…")
            self.controller.cancel_leave()
            return
        self._leave_pending = True
        self.pages.lobby.set_leave_pending(True)
        self.pages.table.set_leave_pending(True)
        self.statusBar().showMessage("Leave requested…")
        self.controller.request_leave()

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
            self.pages.lobby.update_table(payload, self.controller.username)
            self.pages.table.set_table_context(payload.get("table_id"))
        elif event == "lobby_status":
            self.pages.lobby.set_status(payload.get("message", "Waiting…"))
        elif event == "seat_required":
            self._choose_seat(payload)
        elif event == "state":
            state = payload.get("state", {})
            table = payload.get("table")
            self.pages.table.update_state(state, table, self.controller.username)
            self.pages.lobby.update_table(table, self.controller.username)
            self.pages.setCurrentWidget(self.pages.table)
        elif event == "action_required":
            self.pages.setCurrentWidget(self.pages.table)
            self.pages.table.set_legal_actions(payload)
        elif event == "action_sent":
            self.pages.table.clear_legal_actions()
        elif event == "run_it_required":
            self.pages.setCurrentWidget(self.pages.table)
            self.pages.table.show_run_it_prompt()
            self._run_it_timer.start(
                max(0, int(payload.get("seconds", 5))) * 1000
            )
        elif event == "orbital_selection_required":
            self._request_orbital_selection(payload)
        elif event == "orbital_vote_required":
            self._request_orbital_vote(payload)
        elif event == "orbital_full":
            if self._orbital_dialog is not None:
                self._orbital_dialog.blockSignals(True)
                self._orbital_dialog.reject()
                self._orbital_dialog = None
            QMessageBox.information(
                self,
                "Special game full",
                payload.get("message", "Max players reached. You will sit out."),
            )
        elif event == "run_it_vote_sent":
            self._run_it_timer.stop()
            self.pages.table.hide_run_it_prompt()
        elif event == "message":
            if payload == "New hand started.":
                self._showdown_timer.stop()
                self.pages.table.start_new_hand()
            else:
                self.pages.table.append_history(payload)
        elif event == "chat":
            self.pages.table.append_chat_message(payload)
        elif event == "chat_history":
            self.pages.table.set_chat_history(payload)
        elif event == "aof_discard_required":
            self._request_aof_discard(payload)
        elif event == "terminator_board_required":
            self._request_terminator_board(payload)
        elif event == "aof_discarded":
            if self._aof_dialog is not None:
                self._aof_dialog.accept()
                self._aof_dialog = None
        elif event == "hand_history":
            self.pages.table.set_hand_history(payload)
            self.pages.setCurrentWidget(self.pages.table)
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
        elif event == "leave_scheduled":
            message = str(payload) or (
                "You will leave automatically after the current hand."
            )
            self._leave_pending = True
            self.pages.table.set_leave_pending(True)
            self.pages.table.append_history(message)
            self.statusBar().showMessage(message)
        elif event == "leave_cancelled":
            message = str(payload) or "Leave cancelled."
            self._leave_pending = False
            self.pages.lobby.set_leave_pending(False)
            self.pages.table.set_leave_pending(False)
            self.pages.table.append_history(message)
            self.statusBar().showMessage(message, 5000)
        elif event == "left_table":
            self._leave_pending = False
            self.statusBar().showMessage(str(payload), 3000)
            self._leave()
        elif event == "allocator_required":
            self._request_allocation(payload)
        elif event == "allocator_locked":
            if self._allocator_dialog is not None:
                self._allocator_dialog.lock()
        elif event == "name_required":
            self._request_new_name(str(payload))
        elif event == "table_id_required":
            self._request_table_id(str(payload))
        elif event == "error":
            self._leave_pending = False
            self.pages.lobby.set_leave_pending(False)
            self.pages.table.set_leave_pending(False)
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
            self._leave_pending = False
            self.statusBar().showMessage(str(payload))
            self.pages.menu.set_status(str(payload))
            self.pages.setCurrentWidget(self.pages.menu)

    def _choose_seat(self, payload):
        seats = payload.get("available_seats", [])
        if not seats:
            return
        self.pages.lobby.request_seat_selection(payload.get("table"), seats)
        self.pages.setCurrentWidget(self.pages.lobby)

    def _select_seat(self, seat_number):
        self.pages.lobby.clear_seat_selection()
        self.pages.lobby.set_status(f"Taking seat…")
        self.controller.choose_seat(int(seat_number))

    def _submit_run_it_vote(self, choice):
        try:
            self.controller.submit_run_it_vote(choice)
        except (ConnectionError, OSError, RuntimeError, ValueError) as error:
            self.pages.table.hide_run_it_prompt()
            self.pages.table.append_history(f"Run-it vote failed: {error}")

    def _submit_chat(self, message):
        try:
            self.controller.submit_chat(message)
        except (ConnectionError, OSError, RuntimeError, ValueError) as error:
            self.statusBar().showMessage(f"Chat failed: {error}", 5000)

    def _request_aof_discard(self, payload):
        if self._aof_dialog is not None:
            self._aof_dialog.accept()
        dialog = AOFDiscardDialog(
            payload.get("hand", []),
            self,
            game_name=payload.get("game", "AOF"),
        )
        dialog.discarded.connect(self.controller.submit_aof_discard)
        self._aof_dialog = dialog
        dialog.show()

    def _request_orbital_selection(self, payload):
        dialog = OrbitalSelectionDialog(
            payload.get("available_players", 2),
            payload.get("big_blind", 2),
            self,
        )
        dialog.selected.connect(self.controller.submit_orbital_selection)
        dialog.rejected.connect(self.controller.cancel_orbital_selection)
        self._orbital_dialog = dialog
        dialog.finished.connect(lambda _result: setattr(self, "_orbital_dialog", None))
        dialog.show()

    def _request_orbital_vote(self, payload):
        dialog = OrbitalInvitationDialog(
            payload.get("config", {}),
            payload.get("joined", 1),
            payload.get("quota", 2),
            self,
        )
        dialog.decided.connect(self.controller.submit_orbital_vote)
        dialog.rejected.connect(lambda: self.controller.submit_orbital_vote(False))
        self._orbital_dialog = dialog
        dialog.finished.connect(lambda _result: setattr(self, "_orbital_dialog", None))
        dialog.show()

    def _request_terminator_board(self, payload):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Terminate a board")
        dialog.setText("Choose the board whose ranks will be decimated.")
        dialog.setInformativeText(
            "Top: " + ", ".join(payload.get("top_board", []))
            + "\nBottom: " + ", ".join(payload.get("bottom_board", []))
        )
        top_button = dialog.addButton("Terminate Top", QMessageBox.ButtonRole.DestructiveRole)
        bottom_button = dialog.addButton("Terminate Bottom", QMessageBox.ButtonRole.DestructiveRole)
        dialog.exec()
        self.controller.submit_terminator_board(
            "bottom" if dialog.clickedButton() is bottom_button else "top"
        )

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
        minimum = float(request.get("minimum", 0.01))
        amount.setRange(minimum, 1_000_000_000)
        amount.setDecimals(2)
        amount.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        amount.setValue(
            float(request.get("default_amount", self.controller.buy_in))
        )
        form = QFormLayout()
        form.addRow(f"Rebuy amount (min {minimum:g})", amount)
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
        allocator_details = result.get("allocator_details")
        if allocator_details:
            self._show_allocator_showdown(
                allocator_details,
                result.get("payouts", {}),
            )
        else:
            self.pages.table.show_showdown_hands(result.get("hands", []))
            board_results = result.get("double_board_results")
            if board_results and len(board_results) == 2:
                self.pages.table.show_double_board_result(board_results[0])
                QTimer.singleShot(
                    5000,
                    lambda detail=dict(board_results[1]):
                        self.pages.table.show_double_board_result(detail),
                )
                QTimer.singleShot(
                    5650,
                    lambda awards=dict(result.get("payouts", {})):
                        self.pages.table.show_payouts(awards),
                )
            else:
                runout_boards = result.get("runout_boards")
                if runout_boards:
                    self.pages.table.show_runout_boards(runout_boards)
                self.pages.table.show_payouts(result.get("payouts", {}))
                spotlight_cards = result.get("spotlight_cards")
                if spotlight_cards:
                    hand_name = result.get("hand_name", "")
                    QTimer.singleShot(
                        650,
                        lambda cards=list(spotlight_cards), name=hand_name:
                            self.pages.table.spotlight_showdown(cards, name),
                    )
        self._showdown_seconds = max(0, int(result.get("display_seconds", 3)))
        self._show_showdown_timer()
        self._showdown_timer.start()

    def _show_allocator_showdown(self, details, payouts):
        stages = (
            (0, "Top Board", details.get("top", {}), False),
            (5000, "Bottom Board", details.get("bottom", {}), False),
            (10000, "Hand Strength", details.get("hand_strength", {}), True),
        )
        for delay, title, stage, is_strength in stages:
            QTimer.singleShot(
                delay,
                lambda data=stage, name=title, strength=is_strength:
                    self.pages.table.show_allocator_stage(data, name, strength),
            )
            QTimer.singleShot(
                delay + 650,
                lambda data=stage, name=title, strength=is_strength:
                    self.pages.table.spotlight_allocator_stage(
                        data, name, strength
                    ),
            )
        QTimer.singleShot(
            10650,
            lambda awards=dict(payouts): self.pages.table.show_payouts(awards),
        )

    def _tick_showdown_timer(self):
        self._showdown_seconds -= 1
        if self._showdown_seconds <= 0:
            self._showdown_timer.stop()
            self.statusBar().clearMessage()
            return
        self._show_showdown_timer()

    def _show_showdown_timer(self):
        self.statusBar().showMessage(
            f"Next hand in {self._showdown_seconds}s"
        )

    def _request_allocation(self, payload):
        if self._allocator_dialog is not None:
            self._allocator_dialog.raise_()
            self._allocator_dialog.activateWindow()
            return
        dialog = AllocatorDialog(
            payload.get("hand", []),
            payload.get("top_board", []),
            payload.get("bottom_board", []),
            self,
        )
        self._allocator_dialog = dialog
        dialog.submitted.connect(self.controller.submit_allocator_allocation)
        dialog.ready_cancelled.connect(self.controller.cancel_allocator_ready)
        dialog.finished.connect(lambda _result: setattr(self, "_allocator_dialog", None))
        dialog.open()
