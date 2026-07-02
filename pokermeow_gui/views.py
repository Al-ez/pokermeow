from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import PORT


CARD_STYLE = """
    QLabel {
        background: #f8fafc;
        color: #111827;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 8px 5px;
        min-width: 26px;
        font-weight: 700;
    }
"""

SUIT_SYMBOLS = {
    "clubs": "\u2663",
    "diamonds": "\u2666",
    "hearts": "\u2665",
    "spades": "\u2660",
}


def compact_card_text(card):
    card_text = str(card)
    rank, separator, suit = card_text.partition(" of ")
    if not separator:
        return card_text
    return f"{rank}{SUIT_SYMBOLS.get(suit.lower(), suit)}"


def display_amount(value):
    try:
        amount = Decimal(str(value))
        if amount.is_finite():
            return format(amount.normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        pass
    return str(value)


class CardRow(QWidget):
    def __init__(self, empty_text="No cards", parent=None):
        super().__init__(parent)
        self.empty_text = empty_text
        self.row_layout = QHBoxLayout(self)
        self.row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.set_cards([])

    def set_cards(self, cards):
        while self.row_layout.count():
            item = self.row_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not cards:
            label = QLabel(self.empty_text)
            label.setObjectName("muted")
            self.row_layout.addWidget(label)
            return
        for card in cards:
            full_text = str(card)
            label = QLabel(compact_card_text(card))
            label.setToolTip(full_text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(CARD_STYLE)
            self.row_layout.addWidget(label)


class MainMenuView(QWidget):
    connect_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(80, 45, 80, 45)
        root.addStretch()

        title = QLabel("PokerMeow")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Play your existing multiplayer poker game with a desktop UI")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        root.addWidget(subtitle)

        connection_box = QGroupBox("Connection")
        form = QFormLayout(connection_box)
        self.host = QLineEdit("127.0.0.1")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(PORT)
        self.username = QLineEdit()
        self.username.setPlaceholderText("Your display name")
        self.table_id = QLineEdit()
        self.table_id.setPlaceholderText("Required when joining, e.g. A1B2")
        self.buy_in = QDoubleSpinBox()
        self.buy_in.setRange(0.01, 1_000_000_000)
        self.buy_in.setDecimals(2)
        self.buy_in.setValue(1000)
        form.addRow("Server IP", self.host)
        form.addRow("Port", self.port)
        form.addRow("Username", self.username)
        form.addRow("Table ID", self.table_id)
        form.addRow("Buy-in", self.buy_in)
        root.addWidget(connection_box)

        host_box = QGroupBox("New table settings")
        host_form = QFormLayout(host_box)
        self.game = QComboBox()
        self.game.addItem("No-Limit Texas Hold'em", "nlh")
        self.game.addItem("Pot-Limit Omaha", "plo")
        self.game.addItem("Allocator", "allocator")
        self.seats = QSpinBox()
        self.seats.setRange(2, 10)
        self.seats.setValue(6)
        self.big_blind = QDoubleSpinBox()
        self.big_blind.setRange(0.01, 1_000_000)
        self.big_blind.setValue(2)
        self.bomb_ante = QSpinBox()
        self.bomb_ante.setRange(1, 1_000_000)
        self.bomb_ante.setValue(10)
        host_form.addRow("Game", self.game)
        host_form.addRow("Seats", self.seats)
        host_form.addRow("Big blind", self.big_blind)
        host_form.addRow("Allocator ante", self.bomb_ante)
        root.addWidget(host_box)

        buttons = QHBoxLayout()
        host_button = QPushButton("Host Game")
        host_button.setObjectName("primary")
        join_button = QPushButton("Join Game")
        buttons.addWidget(host_button)
        buttons.addWidget(join_button)
        root.addLayout(buttons)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status)
        root.addStretch()

        host_button.clicked.connect(lambda: self._submit("create"))
        join_button.clicked.connect(lambda: self._submit("join"))
        self.game.currentIndexChanged.connect(self._game_changed)
        self._game_changed()

    def set_status(self, text):
        self.status.setText(text)

    def _game_changed(self):
        allocator = self.game.currentData() == "allocator"
        self.bomb_ante.setEnabled(allocator)
        self.big_blind.setEnabled(not allocator)
        self.seats.setMaximum(10 if self.game.currentData() == "nlh" else 7)

    def _submit(self, mode):
        config = {
            "game": self.game.currentData(),
            "max_seats": self.seats.value(),
        }
        if config["game"] == "allocator":
            config["bomb_pot_ante"] = self.bomb_ante.value()
        else:
            config["big_blind"] = self.big_blind.value()
        self.connect_requested.emit(
            {
                "host": self.host.text().strip(),
                "port": self.port.value(),
                "username": self.username.text().strip(),
                "mode": mode,
                "table_id": self.table_id.text().strip(),
                "buy_in": self.buy_in.value(),
                "table_config": config,
            }
        )


class LobbyView(QWidget):
    leave_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        heading = QHBoxLayout()
        self.title = QLabel("Lobby")
        self.title.setObjectName("sectionTitle")
        self.table_id = QLabel("Table —")
        self.table_id.setObjectName("pill")
        heading.addWidget(self.title)
        heading.addStretch()
        heading.addWidget(self.table_id)
        root.addLayout(heading)

        self.status = QLabel("Connecting…")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.players = QTreeWidget()
        self.players.setHeaderLabels(["Seat", "Player", "Ready status", "Stack"])
        self.players.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.players)

        note = QLabel(
            "PokerMeow starts a hand automatically when two seated players are present."
        )
        note.setObjectName("muted")
        root.addWidget(note)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start Game — automatic")
        self.start_button.setEnabled(False)
        leave = QPushButton("Leave")
        controls.addWidget(self.start_button)
        controls.addStretch()
        controls.addWidget(leave)
        root.addLayout(controls)
        leave.clicked.connect(self.leave_requested)

    def configure(self, is_host):
        self.start_button.setVisible(is_host)

    def set_status(self, text):
        self.status.setText(text)

    def set_table_id(self, table_id):
        self.table_id.setText(f"Table {table_id or '—'}")

    def update_table(self, table):
        if not table:
            return
        self.set_table_id(table.get("table_id", ""))
        self.players.clear()
        for seat in table.get("seats", []):
            status = seat.get("status", "open")
            ready = {
                "seated": "Ready",
                "reserved": "Next hand",
                "open": "Open",
                "closed": "Closed",
            }.get(status, status.title())
            item = QTreeWidgetItem(
                [
                    str(seat.get("seat", "")),
                    str(seat.get("player") or "—"),
                    ready,
                    str(seat.get("stack") if seat.get("stack") is not None else "—"),
                ]
            )
            self.players.addTopLevelItem(item)


class TableView(QWidget):
    action_requested = Signal(str, float)
    leave_requested = Signal()

    ACTIONS = ("fold", "check", "call", "bet", "raise", "all_in")

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QGridLayout(self)

        top = QHBoxLayout()
        self.table_name = QLabel("Poker table")
        self.table_name.setObjectName("sectionTitle")
        self.turn = QLabel("Waiting for action")
        top.addWidget(self.table_name)
        top.addStretch()
        top.addWidget(self.turn)
        root.addLayout(top, 0, 0, 1, 2)

        felt = QGroupBox("Cards")
        felt_layout = QVBoxLayout(felt)
        cards_heading = QHBoxLayout()
        cards_heading.addStretch()
        self.pot = QLabel("Pot: 0")
        self.pot.setObjectName("pill")
        cards_heading.addWidget(self.pot)
        felt_layout.addLayout(cards_heading)
        self.board_label = QLabel("Community cards")
        self.board = CardRow()
        self.top_board_label = QLabel("Top board")
        self.top_board = CardRow()
        self.bottom_board_label = QLabel("Bottom board")
        self.bottom_board = CardRow()
        felt_layout.addWidget(self.board_label)
        felt_layout.addWidget(self.board)
        felt_layout.addWidget(self.top_board_label)
        felt_layout.addWidget(self.top_board)
        felt_layout.addWidget(self.bottom_board_label)
        felt_layout.addWidget(self.bottom_board)

        self.hole_label = QLabel("Your hole cards")
        self.hole_label.setObjectName("subheading")
        self.hole_cards = CardRow("Cards are dealt at the start of a hand")
        felt_layout.addSpacing(12)
        felt_layout.addWidget(self.hole_label)
        felt_layout.addWidget(self.hole_cards)
        root.addWidget(felt, 1, 0)

        players_box = QGroupBox("Players")
        players_layout = QVBoxLayout(players_box)
        self.players = QTreeWidget()
        self.players.setHeaderLabels(
            ["Player", "Stack", "Bet", "Status", "Cards", "Hand"]
        )
        self.players.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        players_layout.addWidget(self.players)
        root.addWidget(players_box, 2, 0)

        side = QVBoxLayout()
        history_box = QGroupBox("Action history")
        history_layout = QVBoxLayout(history_box)
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        history_layout.addWidget(self.history)
        side.addWidget(history_box, 2)

        chat_box = QGroupBox("Chat")
        chat_layout = QVBoxLayout(chat_box)
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Server and table messages appear here.")
        chat_controls = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Player chat requires server protocol support")
        self.chat_input.setEnabled(False)
        send_chat = QPushButton("Send")
        send_chat.setEnabled(False)
        send_chat.setToolTip("The current PokerMeow server has no chat message type.")
        chat_controls.addWidget(self.chat_input)
        chat_controls.addWidget(send_chat)
        chat_layout.addWidget(self.chat)
        chat_layout.addLayout(chat_controls)
        side.addWidget(chat_box, 1)
        root.addLayout(side, 1, 1, 2, 1)

        actions = QGroupBox("Betting controls")
        actions_layout = QHBoxLayout(actions)
        self.action_buttons = {}
        for action in self.ACTIONS:
            button = QPushButton(action.replace("_", " ").title())
            button.setEnabled(False)
            button.clicked.connect(
                lambda checked=False, selected=action: self._send_action(selected)
            )
            self.action_buttons[action] = button
            actions_layout.addWidget(button)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 1_000_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("Amount: ")
        self.amount.setEnabled(False)
        actions_layout.addWidget(self.amount)
        leave = QPushButton("Leave")
        leave.clicked.connect(self.leave_requested)
        actions_layout.addWidget(leave)
        root.addWidget(actions, 3, 0, 1, 2)
        root.setColumnStretch(0, 3)
        root.setColumnStretch(1, 2)

        self.current_table_id = None
        self._set_allocator_boards(False)

    def update_state(self, state, table, username):
        self.pot.setText(f"Pot: {state.get('pot', 0)}")
        if table:
            self.set_table_context(table.get("table_id"))
            self.table_name.setText(
                f"{table.get('game', 'Poker')} · {table.get('table_id', '')}"
            )
        allocator = "top_board" in state
        self._set_allocator_boards(allocator)
        if allocator:
            self.top_board.set_cards(state.get("top_board", []))
            self.bottom_board.set_cards(state.get("bottom_board", []))
        else:
            self.board.set_cards(state.get("board", []))

        self.players.clear()
        own_hand = []
        dealer = state.get("dealer")
        for name, player in state.get("players", {}).items():
            statuses = []
            if name == dealer:
                statuses.append("Dealer")
            if player.get("folded"):
                statuses.append("Folded")
            if player.get("all_in"):
                statuses.append("All-in")
            if name == username:
                statuses.append("You")
                own_hand = player.get("hand", [])
            item = QTreeWidgetItem(
                [
                    name,
                    str(player.get("stack", 0)),
                    str(player.get("current_bet", 0)),
                    ", ".join(statuses) or "Playing",
                    "",
                    "",
                ]
            )
            if name == dealer:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            self.players.addTopLevelItem(item)
        self.hole_cards.set_cards(own_hand)

    def show_showdown_hands(self, hands):
        hands_by_player = {
            hand.get("player"): hand
            for hand in hands
            if hand.get("player")
        }
        for index in range(self.players.topLevelItemCount()):
            item = self.players.topLevelItem(index)
            hand_info = hands_by_player.get(item.text(0))
            if hand_info is None:
                item.setText(4, "")
                item.setText(5, "")
                continue
            cards = " ".join(
                compact_card_text(card)
                for card in hand_info.get("hand", [])
            )
            rankings = hand_info.get("rankings")
            if rankings:
                ranking = (
                    f"Top {rankings.get('top', '—')} / "
                    f"Bottom {rankings.get('bottom', '—')} / "
                    f"{rankings.get('hand_strength', '—')} / "
                    f"{rankings.get('total', '—')} pts"
                )
            else:
                ranking = hand_info.get("hand_name", "Unknown hand")
            item.setText(4, cards)
            item.setText(5, ranking)
            item.setToolTip(4, cards)
            item.setToolTip(5, ranking)

    def set_legal_actions(self, request):
        legal = set(request.get("legal_actions", []))
        for action, button in self.action_buttons.items():
            button.setEnabled(action in legal)
        to_call = request.get("to_call", 0)
        call_text = display_amount(to_call)
        self.action_buttons["call"].setText(
            f"Call {call_text}" if "call" in legal else "Call"
        )
        uses_amount = bool(legal.intersection({"bet", "raise"}))
        self.amount.setEnabled(uses_amount)
        minimum = request.get("min_raise_to", request.get("min_raise", 0)) or 0
        maximum = request.get("max_raise_to", request.get("max_bet"))
        self.amount.setMinimum(float(minimum))
        self.amount.setMaximum(float(maximum) if maximum is not None else 1_000_000_000)
        self.amount.setValue(float(minimum))
        self.turn.setText(f"Your turn \u00b7 call {call_text}")
        self.turn.setObjectName("turnActive")
        self.turn.style().unpolish(self.turn)
        self.turn.style().polish(self.turn)

    def clear_legal_actions(self):
        for button in self.action_buttons.values():
            button.setEnabled(False)
        self.action_buttons["call"].setText("Call")
        self.amount.setEnabled(False)
        self.turn.setText("Waiting for another player")

    def append_history(self, text):
        if text:
            self.history.append(str(text))

    def start_new_hand(self):
        self.history.clear()
        self.append_history("New hand started.")

    def set_table_context(self, table_id):
        if not table_id or table_id == self.current_table_id:
            return
        self.current_table_id = table_id
        self.history.clear()

    def reset_session(self):
        self.current_table_id = None
        self.history.clear()
        self.chat.clear()
        self.clear_legal_actions()

    def append_chat(self, text):
        if text:
            self.chat.append(str(text))

    def _send_action(self, action):
        amount = self.amount.value() if action in {"bet", "raise"} else 0
        self.action_requested.emit(action, amount)
        self.clear_legal_actions()
        suffix = f" {amount:g}" if action in {"bet", "raise"} else ""
        self.append_history(f"You: {action}{suffix}")

    def _set_allocator_boards(self, allocator):
        self.board_label.setVisible(not allocator)
        self.board.setVisible(not allocator)
        self.top_board_label.setVisible(allocator)
        self.top_board.setVisible(allocator)
        self.bottom_board_label.setVisible(allocator)
        self.bottom_board.setVisible(allocator)


class PokerStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.menu = MainMenuView()
        self.lobby = LobbyView()
        self.table = TableView()
        self.addWidget(self.menu)
        self.addWidget(self.lobby)
        self.addWidget(self.table)
