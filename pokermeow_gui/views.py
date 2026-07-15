from html import escape
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QGraphicsOpacityEffect,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
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


def compact_card_html(card):
    rank, suit = card_rank_suit(card)
    suit_size = 27 if suit == "♣" else 22
    return (
        f'<span style="font-size:22px; font-weight:800;">{escape(str(rank))}</span>'
        f'<span style="font-family:Segoe UI Symbol; font-size:{suit_size}px; '
        f'font-weight:1000;">{escape(str(suit))}</span>'
    )


def stacked_card_text(card):
    card_text = str(card)
    rank, separator, suit = card_text.partition(" of ")
    if not separator:
        return card_text
    return f"{rank}\n{SUIT_SYMBOLS.get(suit.lower(), suit)}"


def stacked_card_html(card):
    rank, suit = card_rank_suit(card)
    suit_size = 18 if suit == "♣" else 15
    return (
        f'<div style="font-size:10px; line-height:11px;">{escape(str(rank))}</div>'
        f'<div style="font-family:Segoe UI Symbol; font-size:{suit_size}px; '
        f'line-height:18px; font-weight:1000;">{escape(str(suit))}</div>'
    )


def card_rank_suit(card):
    card_text = str(card)
    rank, separator, suit = card_text.partition(" of ")
    if not separator:
        return card_text, ""
    return rank, SUIT_SYMBOLS.get(suit.lower(), suit)


def is_red_card(card):
    card_text = str(card).lower()
    return card_text.endswith("hearts") or "♥" in card_text


def card_display_color(card, muted=False):
    card_text = str(card).lower()
    if card_text.endswith("hearts") or "♥" in card_text:
        return "#991b1b" if muted else "#dc2626"
    if card_text.endswith("diamonds") or "♦" in card_text:
        return "#1e3a8a" if muted else "#2563eb"
    if card_text.endswith("clubs") or "♣" in card_text:
        return "#166534" if muted else "#15803d"
    return "#334155" if muted else "#111827"


def display_amount(value):
    try:
        amount = Decimal(str(value))
        if amount.is_finite():
            return format(amount.normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        pass
    return str(value)


def cards_text(cards):
    return " ".join(compact_card_text(card) for card in cards) if cards else "—"


def card_cell_html(text, color="#f8fafc", offset=0):
    margin = 0 if offset == 0 else -12
    content = escape(str(text)).replace("\n", "<br>")
    return (
        '<span style="'
        "display:inline-block;"
        "background:#f8fafc;"
        f"color:{color};"
        "border:1px solid #cbd5e1;"
        "border-radius:6px;"
        "width:34px;"
        "height:42px;"
        "padding:3px 0 0 4px;"
        f"margin-left:{margin}px;"
        "font-weight:800;"
        "font-size:10px;"
        "line-height:10px;"
        "text-align:left;"
        "vertical-align:top;"
        '">'
        f"{content}</span>"
    )


def cards_html(cards, spotlight=None):
    if not cards:
        return '<span style="color:#64748b;">—</span>'
    cells = []
    spotlight = {str(card) for card in spotlight} if spotlight is not None else None
    for card in cards:
        rank, suit = card_rank_suit(card)
        highlighted = spotlight is None or str(card) in spotlight
        color = card_display_color(card, muted=not highlighted)
        background = "#fffbea" if spotlight is not None and highlighted else (
            "#cbd5e1" if not highlighted else "#f8fafc"
        )
        border = "#fde047" if spotlight is not None and highlighted else "#94a3b8"
        suit_size = 18 if suit == "♣" else 15
        cells.append(
            '<td style="'
            f"background:{background};"
            f"color:{color};"
            f"border:2px solid {border};"
            "border-radius:7px;"
            "width:34px;"
            "height:44px;"
            "padding:3px 4px;"
            "font-weight:900;"
            "text-align:center;"
            "vertical-align:middle;"
            '">'
            f'<div style="font-size:13px; line-height:15px;">{escape(str(rank))}</div>'
            f'<div style="font-family:Segoe UI Symbol; font-size:{suit_size}px; '
            f'line-height:18px; font-weight:1000;">{escape(str(suit))}</div>'
            "</td>"
        )
    return (
        '<table align="center" cellspacing="3" cellpadding="0"><tr>'
        + "".join(cells)
        + "</tr></table>"
    )


def card_backs_html(count):
    try:
        total = max(0, int(count))
    except (TypeError, ValueError):
        total = 0
    cells = [
        card_cell_html("\U0001F0A0", color="#bfdbfe", offset=index)
        for index in range(total)
    ]
    return (
        '<div align="center" style="white-space:nowrap;">'
        + "".join(cells)
        + "</div>"
    )


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
            label = QLabel(compact_card_html(card))
            label.setToolTip(full_text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            style = CARD_STYLE
            style += f"\nQLabel {{ color: {card_display_color(card)}; }}"
            label.setStyleSheet(style)
            self.row_layout.addWidget(label)


class PokerSeatWidget(QFrame):
    clicked = Signal(int)

    def __init__(self, seat_number, show_game_details=False, parent=None):
        super().__init__(parent)
        self.seat_number = seat_number
        self.show_game_details = show_game_details
        self.setObjectName("pokerSeat")
        self.setMinimumSize(72, 40)
        self.setMaximumSize(176, 62)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(0)

        self.player_label = QLabel("Open")
        self.player_label.setObjectName("seatPlayer")
        self.player_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.player_label)

        self.stack_label = QLabel("")
        self.stack_label.setObjectName("seatStack")
        self.stack_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack_label.setWordWrap(True)
        layout.addWidget(self.stack_label)
        self.player_label.setStyleSheet("background: transparent; border: none;")
        self.stack_label.setStyleSheet("background: transparent; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.seat_number)
        super().mousePressEvent(event)

    def set_pickable(self, pickable):
        self.setProperty("pickable", bool(pickable))
        self.style().unpolish(self)
        self.style().polish(self)

    def update_seat(self, seat, player=None, username="", dealer=None):
        status = seat.get("status", "open")
        name = seat.get("player")
        occupied = bool(name)
        self.setProperty("occupied", occupied)
        self.setProperty("hero", False)
        self.style().unpolish(self)
        self.style().polish(self)

        self.player_label.setText(name or self._empty_label(status))
        self.player_label.setToolTip(name or "")
        self.stack_label.setText(self._stack_text(seat, player))

    def _empty_label(self, status):
        return {
            "open": "Open",
            "closed": "Closed",
            "reserved": "Next hand",
        }.get(status, status.title())

    def _stack_text(self, seat, player):
        stack = player.get("stack") if player else seat.get("stack")
        if stack is None:
            return ""
        return display_amount(stack)


class CardFanWidget(QWidget):
    CARD_W = 34
    CARD_H = 42
    STEP = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self.card_labels = []
        self._animations = []
        self.setMinimumSize(118, self.CARD_H + 2)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

    def set_cards(self, cards):
        self._set_card_texts(
            [
                (
                    stacked_card_html(card),
                    card_display_color(card),
                    str(card),
                )
                for card in cards
            ]
        )

    def spotlight(self, cards):
        spotlight = {str(card) for card in cards}
        self._animations = []
        for label in self.card_labels:
            highlighted = label.toolTip() in spotlight
            color = card_display_color(label.toolTip())
            label.setStyleSheet(
                "QLabel {"
                f"background: {'#fffbea' if highlighted else '#cbd5e1'};"
                f"color: {color if highlighted else card_display_color(label.toolTip(), muted=True)};"
                f"border: 2px solid {'#fde047' if highlighted else '#94a3b8'};"
                "border-radius: 6px; padding: 3px 0 0 4px;"
                "font-weight: 800; font-size: 10px;"
                "}"
            )
            if highlighted:
                effect = QGraphicsOpacityEffect(label)
                label.setGraphicsEffect(effect)
                animation = QPropertyAnimation(effect, b"opacity", self)
                animation.setDuration(550)
                animation.setStartValue(0.4)
                animation.setEndValue(1.0)
                animation.setEasingCurve(QEasingCurve.Type.OutCubic)
                animation.start()
                self._animations.append(animation)
            else:
                # Muted colors create the shadow. Keeping the card opaque
                # prevents overlapping cards from becoming brighter.
                label.setGraphicsEffect(None)

    def set_card_backs(self, count):
        try:
            total = max(0, int(count))
        except (TypeError, ValueError):
            total = 0
        self._set_card_texts([("\U0001F0A0", "#bfdbfe", "") for _ in range(total)])

    def clear(self):
        self._set_card_texts([])

    def _set_card_texts(self, cards):
        while len(self.card_labels) > len(cards):
            label = self.card_labels.pop()
            label.deleteLater()
        while len(self.card_labels) < len(cards):
            label = QLabel(self)
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.card_labels.append(label)
        for label, (text, color, tooltip) in zip(self.card_labels, cards):
            label.setGraphicsEffect(None)
            label.setText(text)
            label.setToolTip(tooltip)
            label.setStyleSheet(
                "QLabel {"
                "background: #f8fafc;"
                f"color: {color};"
                "border: 1px solid #cbd5e1;"
                "border-radius: 6px;"
                "padding: 3px 0 0 4px;"
                "font-weight: 800;"
                "font-size: 10px;"
                "}"
            )
            label.show()
        self.setVisible(bool(cards))
        self._layout_cards()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_cards()

    def _layout_cards(self):
        total = len(self.card_labels)
        if not total:
            return
        fan_w = self.CARD_W + self.STEP * (total - 1)
        start_x = max(0, int((self.width() - fan_w) / 2))
        start_y = max(0, int((self.height() - self.CARD_H) / 2))
        for index, label in enumerate(self.card_labels):
            label.setGeometry(
                start_x + self.STEP * index,
                start_y,
                self.CARD_W,
                self.CARD_H,
            )
            label.raise_()


class PokerActionSpot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tableAction")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMinimumSize(126, 54)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)
        layout.addStretch(1)
        self.dealer_label = QLabel("")
        self.dealer_label.setObjectName("dealerButton")
        self.dealer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dealer_label.setVisible(False)
        self.cards_label = CardFanWidget()
        self.hand_label = QLabel("")
        self.hand_label.setObjectName("seatHand")
        self.hand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hand_label.setWordWrap(True)
        self.hand_label.setStyleSheet("background: transparent; border: none;")
        self.hand_label.setVisible(False)
        layout.addWidget(self.dealer_label)
        layout.addWidget(self.cards_label)
        layout.addWidget(self.hand_label)

    def update_action(self, player=None, dealer=False, is_hero=False):
        if not player:
            self.clear()
            return
        self.dealer_label.setVisible(False)
        if player.get("all_in") and not player.get("folded"):
            hand_text = "All-in"
        else:
            hand_text = ""
        self.hand_label.setText(hand_text)
        self.hand_label.setVisible(bool(hand_text))
        self._update_cards(player, is_hero=is_hero)
        self.hand_label.setToolTip("")

    def show_showdown(self, hand_info):
        self.cards_label.set_cards(hand_info.get("hand", []))
        self.hand_label.setText("")
        self.hand_label.setVisible(False)
        self.hand_label.setToolTip("")

    def clear(self):
        self.dealer_label.setText("")
        self.dealer_label.setVisible(False)
        self.cards_label.clear()
        self.hand_label.setText("")
        self.hand_label.setVisible(False)
        self.hand_label.setToolTip("")

    def _update_cards(self, player, is_hero=False):
        if player.get("folded") and not is_hero:
            self.cards_label.clear()
            return
        if player.get("hand"):
            self.cards_label.set_cards(player.get("hand", []))
            return
        hand_size = player.get("hand_size")
        if hand_size:
            self.cards_label.set_card_backs(hand_size)
            return
        self.cards_label.clear()

    @staticmethod
    def _decimal(value):
        try:
            amount = Decimal(str(value))
            if amount.is_finite():
                return amount
        except (InvalidOperation, TypeError, ValueError):
            pass
        return Decimal(0)


class PokerBetSpot(QLabel):
    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("tableActionTop")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMinimumSize(48, 24)

    def set_amount(self, amount):
        try:
            parsed = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            parsed = Decimal(0)
        self.setStyleSheet("background: transparent; border: none;")
        self.setText(display_amount(amount) if parsed > 0 else "")
        self.setVisible(parsed > 0)

    def show_payout(self, amount):
        try:
            parsed = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            parsed = Decimal(0)
        if parsed <= 0:
            return
        self.setText(f"+{display_amount(parsed)}")
        self.setStyleSheet(
            "background: #14532d; color: #bbf7d0;"
            "border: 2px solid #4ade80; border-radius: 10px;"
            "padding: 4px 10px; font-size: 16px; font-weight: 900;"
        )
        self.setVisible(True)


class PokerTableDisplay(QWidget):
    seat_clicked = Signal(int)

    POSITIONS = {
        "bottom": (0.50, 0.94),
        "bottom_left": (0.27, 0.90),
        "left_bottom": (0.06, 0.66),
        "left_top": (0.06, 0.26),
        "top_left": (0.27, 0.21),
        "top": (0.50, 0.21),
        "top_right": (0.73, 0.21),
        "right_top": (0.94, 0.26),
        "right_bottom": (0.94, 0.66),
        "bottom_right": (0.73, 0.90),
    }
    BET_POSITIONS = {
        "bottom": (0.50, 0.70),
        "bottom_left": (0.35, 0.68),
        "left_bottom": (0.24, 0.58),
        "left_top": (0.24, 0.36),
        "top_left": (0.35, 0.26),
        "top": (0.50, 0.23),
        "top_right": (0.65, 0.26),
        "right_top": (0.76, 0.36),
        "right_bottom": (0.76, 0.58),
        "bottom_right": (0.65, 0.68),
    }
    POSITION_ORDER = {
        2: ["bottom", "top"],
        3: ["bottom", "left_top", "right_top"],
        4: ["bottom", "left_top", "top", "right_top"],
        5: ["bottom", "left_bottom", "left_top", "top", "right_top"],
        6: ["bottom", "bottom_left", "left_top", "top", "right_top", "bottom_right"],
        7: [
            "bottom",
            "bottom_left",
            "left_top",
            "top_left",
            "top_right",
            "right_top",
            "bottom_right",
        ],
        8: [
            "bottom",
            "bottom_left",
            "left_bottom",
            "left_top",
            "top",
            "right_top",
            "right_bottom",
            "bottom_right",
        ],
        9: [
            "bottom",
            "bottom_left",
            "left_bottom",
            "left_top",
            "top_left",
            "top_right",
            "right_top",
            "right_bottom",
            "bottom_right",
        ],
        10: [
            "bottom",
            "bottom_left",
            "left_bottom",
            "left_top",
            "top_left",
            "top",
            "top_right",
            "right_top",
            "right_bottom",
            "bottom_right",
        ],
    }

    def __init__(self, show_game_details=False, parent=None):
        super().__init__(parent)
        self.show_game_details = show_game_details
        self.seat_widgets = {}
        self.action_widgets = {}
        self.bet_widgets = {}
        self.dealer_widgets = {}
        self.player_seats = {}
        self.display_order = []
        self.pickable_seats = set()
        self.community_cards = []
        self.setMinimumHeight(420 if show_game_details else 360)

        self.felt = QFrame()
        self.felt.setObjectName("pokerFelt")
        self.felt.setParent(self)
        felt_layout = QVBoxLayout(self.felt)
        felt_layout.setContentsMargins(24, 20, 24, 20)
        felt_layout.setSpacing(8)
        self.pot_label = QLabel("Pot: 0")
        self.pot_label.setObjectName("feltPot")
        self.pot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.board_label = QLabel(cards_html([]))
        self.board_label.setTextFormat(Qt.TextFormat.RichText)
        self.board_label.setObjectName("feltBoard")
        self.board_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.winning_hand_label = QLabel("")
        self.winning_hand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.winning_hand_label.setVisible(False)
        self.winning_hand_label.setStyleSheet(
            "background: #facc15; color: #422006;"
            "border: 2px solid #fef08a; border-radius: 10px;"
            "padding: 5px 14px; font-size: 16px; font-weight: 900;"
        )
        felt_layout.addStretch()
        felt_layout.addWidget(self.pot_label)
        felt_layout.addWidget(
            self.winning_hand_label,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        felt_layout.addWidget(self.board_label)
        felt_layout.addStretch()

        for seat_number in range(1, 11):
            widget = PokerSeatWidget(seat_number, show_game_details, self)
            widget.clicked.connect(self._seat_clicked)
            widget.setVisible(False)
            self.seat_widgets[seat_number] = widget
            action = PokerActionSpot(self)
            action.setVisible(False)
            self.action_widgets[seat_number] = action
            bet = PokerBetSpot(self)
            bet.setVisible(False)
            self.bet_widgets[seat_number] = bet
            dealer_badge = QLabel("D", self)
            dealer_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dealer_badge.setStyleSheet(
                "background: #f8fafc; color: #111827;"
                "border: 1px solid #111827; border-radius: 10px;"
                "font-size: 11px; font-weight: 900; padding: 0;"
            )
            dealer_badge.setVisible(False)
            self.dealer_widgets[seat_number] = dealer_badge

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_table()

    def set_pickable_seats(self, seats):
        self.pickable_seats = {int(seat) for seat in seats}
        for seat_number, widget in self.seat_widgets.items():
            widget.set_pickable(seat_number in self.pickable_seats)

    def clear_pickable_seats(self):
        self.set_pickable_seats([])

    def _seat_clicked(self, seat_number):
        if not self.pickable_seats or seat_number in self.pickable_seats:
            self.seat_clicked.emit(seat_number)

    def update_lobby(self, table, username=""):
        seats = self._visible_seats(table)
        self.player_seats = {}
        self.pot_label.setText("Waiting for players")
        self.board_label.setText("")
        self.winning_hand_label.setVisible(False)
        self._set_visible_seats(seats, username)
        for seat in seats:
            seat_number = int(seat.get("seat", 0))
            widget = self.seat_widgets.get(seat_number)
            if widget is None:
                continue
            widget.update_seat(seat)
            self.action_widgets[seat_number].clear()
            self.bet_widgets[seat_number].set_amount(0)
            self.dealer_widgets[seat_number].setVisible(False)
            if seat.get("player"):
                self.player_seats[seat["player"]] = seat_number
        self._layout_table()

    def update_game(self, state, table, username):
        seats = self._visible_seats(table)
        if not seats:
            seats = [
                {
                    "seat": index + 1,
                    "status": "seated",
                    "player": name,
                    "stack": player.get("stack", 0),
                }
                for index, (name, player) in enumerate(
                    state.get("players", {}).items()
                )
            ]
        players = state.get("players", {})
        dealer = state.get("dealer")
        self.player_seats = {}
        self.pot_label.setText(f"Pot: {state.get('pot', 0)}")
        self.community_cards = list(state.get("board", []))
        self.board_label.setText(self._community_cards_html(state))
        self.board_label.setToolTip(self._community_cards_text(state))
        self.winning_hand_label.setVisible(False)
        self._set_visible_seats(seats, username)

        for seat in seats:
            seat_number = int(seat.get("seat", 0))
            widget = self.seat_widgets.get(seat_number)
            if widget is None:
                continue
            name = seat.get("player")
            player = players.get(name, {}) if name else {}
            widget.update_seat(seat, player, username, dealer)
            self.action_widgets[seat_number].setVisible(
                bool(name) and self.show_game_details
            )
            self.action_widgets[seat_number].update_action(
                player if name else None,
                dealer=bool(name and name == dealer),
                is_hero=bool(name and name == username),
            )
            self.bet_widgets[seat_number].set_amount(
                player.get("current_bet", 0) if name else 0
            )
            self.dealer_widgets[seat_number].setVisible(
                bool(name and name == dealer)
            )
            if name:
                self.player_seats[name] = seat_number
        self._layout_table()

    def show_showdown_hands(self, hands):
        for hand_info in hands:
            player = hand_info.get("player")
            seat_number = self.player_seats.get(player)
            widget = self.action_widgets.get(seat_number)
            if widget is not None:
                widget.show_showdown(hand_info)

    def spotlight_showdown(self, cards, hand_name=""):
        for widget in self.action_widgets.values():
            widget.cards_label.spotlight(cards)
        if self.community_cards:
            self.board_label.setText(cards_html(self.community_cards, cards))
        if hand_name:
            self.winning_hand_label.setText(
                str(hand_name).replace("_", " ").title()
            )
            self.winning_hand_label.setVisible(True)

    def show_payouts(self, payouts):
        for player, amount in payouts.items():
            seat_number = self.player_seats.get(player)
            widget = self.bet_widgets.get(seat_number)
            if widget is not None:
                widget.show_payout(amount)
        self._layout_table()

    def _visible_seats(self, table):
        if not table:
            return []
        return [
            seat
            for seat in table.get("seats", [])
            if seat.get("status") != "closed"
        ]

    def _set_visible_seats(self, seats, username=""):
        visible_numbers = [int(seat.get("seat", 0)) for seat in seats]
        visible = set(visible_numbers)
        hero_seat = next(
            (
                int(seat.get("seat", 0))
                for seat in seats
                if username and seat.get("player") == username
            ),
            None,
        )
        if hero_seat in visible_numbers:
            hero_index = visible_numbers.index(hero_seat)
            visible_numbers = visible_numbers[hero_index:] + visible_numbers[:hero_index]
        position_names = self.POSITION_ORDER.get(
            len(visible_numbers),
            self.POSITION_ORDER[10],
        )
        self.display_order = list(zip(visible_numbers, position_names))
        for seat_number, widget in self.seat_widgets.items():
            widget.setVisible(seat_number in visible)
            self.action_widgets[seat_number].setVisible(
                seat_number in visible and self.show_game_details
            )
            self.bet_widgets[seat_number].setVisible(False)
            self.dealer_widgets[seat_number].setVisible(False)

    def _layout_table(self):
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        felt_margin_x = int(width * 0.14)
        felt_margin_y = int(height * 0.26)
        self.felt.setGeometry(
            felt_margin_x,
            felt_margin_y,
            max(width - felt_margin_x * 2, 260),
            max(height - felt_margin_y * 2, 160),
        )

        seats_in_play = max(1, len(self.display_order))
        seat_w = max(72, min(176, int(width * 0.17), int(width / max(4.5, seats_in_play * 0.72))))
        seat_h = max(40, min(58, int(seat_w * 0.44)))
        action_w = max(150, min(210, int(width * 0.21)))
        action_h = max(54, min(76, int(height * 0.13)))
        bet_w = max(72, min(110, int(width * 0.10)))
        bet_h = 28
        for seat_number, position_name in self.display_order:
            seat_x, seat_y = self.POSITIONS[position_name]
            self._place_widget(
                self.seat_widgets[seat_number],
                seat_x,
                seat_y,
                seat_w,
                seat_h,
            )
            seat_geometry = self.seat_widgets[seat_number].geometry()
            card_x = seat_geometry.x() + seat_geometry.width() / 2
            card_y = seat_geometry.y() - action_h / 2 - 2
            self._place_widget(
                self.action_widgets[seat_number],
                card_x / max(self.width(), 1),
                card_y / max(self.height(), 1),
                action_w,
                action_h,
            )
            bet_widget = self.bet_widgets[seat_number]
            marker_w = max(bet_w, min(180, bet_widget.sizeHint().width() + 8))
            marker_h = max(bet_h, min(40, bet_widget.sizeHint().height() + 4))
            self._place_widget(
                bet_widget,
                self._toward_center(seat_x, 0.58),
                self._toward_center(seat_y, 0.58),
                marker_w,
                marker_h,
            )
            self._place_widget(
                self.dealer_widgets[seat_number],
                self._toward_center(seat_x, 0.48),
                self._toward_center(seat_y, 0.48),
                22,
                22,
            )

    def _place_widget(self, widget, x_ratio, y_ratio, width, height):
        x = int(self.width() * x_ratio - width / 2)
        y = int(self.height() * y_ratio - height / 2)
        x = max(0, min(x, max(0, self.width() - width)))
        y = max(0, min(y, max(0, self.height() - height)))
        widget.setGeometry(x, y, width, height)
        widget.raise_()
        self.felt.lower()

    @staticmethod
    def _toward_center(value, fraction):
        return value + (0.5 - value) * fraction

    def _community_cards_html(self, state):
        if "top_board" in state:
            return (
                f"<b>Top:</b> {cards_html(state.get('top_board', []))}"
                "<br>"
                f"<b>Bottom:</b> {cards_html(state.get('bottom_board', []))}"
            )
        return cards_html(state.get("board", []))

    def _community_cards_text(self, state):
        if "top_board" in state:
            return (
                f"Top: {cards_text(state.get('top_board', []))} | "
                f"Bottom: {cards_text(state.get('bottom_board', []))}"
            )
        return cards_text(state.get("board", []))


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

        mode_buttons = QHBoxLayout()
        self.host_mode_button = QPushButton("Host Game")
        self.join_mode_button = QPushButton("Join Game")
        self.host_mode_button.setCheckable(True)
        self.join_mode_button.setCheckable(True)
        mode_buttons.addWidget(self.host_mode_button)
        mode_buttons.addWidget(self.join_mode_button)
        root.addLayout(mode_buttons)

        connection_box = QGroupBox("Connection")
        self.connection_form = QFormLayout(connection_box)
        self.host = QLineEdit("127.0.0.1")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(PORT)
        self.port.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.username = QLineEdit()
        self.username.setPlaceholderText("Your display name")
        self.table_id = QLineEdit()
        self.table_id.setPlaceholderText("Required when joining, e.g. A1B2")
        self.buy_in = QDoubleSpinBox()
        self.buy_in.setRange(0.01, 1_000_000_000)
        self.buy_in.setDecimals(2)
        self.buy_in.setValue(1000)
        self.buy_in.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.connection_form.addRow("Server", self.host)
        self.connection_form.addRow("Port", self.port)
        self.connection_form.addRow("Username", self.username)
        self.connection_form.addRow("Table ID", self.table_id)
        self.connection_form.addRow("Buy-in", self.buy_in)
        root.addWidget(connection_box)

        self.host_box = QGroupBox("New table settings")
        self.host_form = QFormLayout(self.host_box)
        self.game = QComboBox()
        self.game.addItem("No-Limit Texas Hold'em", "nlh")
        self.game.addItem("Pot-Limit Omaha", "plo")
        self.game.addItem("Allocator", "allocator")
        self.seats = QSpinBox()
        self.seats.setRange(2, 10)
        self.seats.setValue(6)
        self.seats.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.big_blind = QDoubleSpinBox()
        self.big_blind.setRange(0.01, 1_000_000)
        self.big_blind.setValue(2)
        self.big_blind.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.bomb_ante = QSpinBox()
        self.bomb_ante.setRange(1, 1_000_000)
        self.bomb_ante.setValue(10)
        self.bomb_ante.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.host_form.addRow("Game", self.game)
        self.host_form.addRow("Seats", self.seats)
        self.host_form.addRow("Big blind", self.big_blind)
        self.host_form.addRow("Ante", self.bomb_ante)
        root.addWidget(self.host_box)

        self.connect_button = QPushButton("Host Game")
        self.connect_button.setObjectName("primary")
        root.addWidget(self.connect_button)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status)
        root.addStretch()

        self.mode = "create"
        self.host_mode_button.clicked.connect(
            lambda: self._set_mode("create")
        )
        self.join_mode_button.clicked.connect(
            lambda: self._set_mode("join")
        )
        self.connect_button.clicked.connect(
            lambda: self._submit(self.mode)
        )
        self.game.currentIndexChanged.connect(self._game_changed)
        self._set_mode("create")
        self._game_changed()

    def set_status(self, text):
        self.status.setText(text)

    def _game_changed(self):
        allocator = self.game.currentData() == "allocator"
        self.host_form.setRowVisible(self.bomb_ante, allocator)
        self.host_form.setRowVisible(self.big_blind, not allocator)
        self.seats.setMaximum(10 if self.game.currentData() == "nlh" else 7)

    def _set_mode(self, mode):
        self.mode = mode
        hosting = mode == "create"
        self.host_mode_button.setChecked(hosting)
        self.join_mode_button.setChecked(not hosting)
        self.connection_form.setRowVisible(self.table_id, not hosting)
        self.host_box.setVisible(hosting)
        self.connect_button.setText("Host Game" if hosting else "Join Game")

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
    seat_selected = Signal(int)

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
        self._seat_selection_active = False
        self.table_display = PokerTableDisplay(show_game_details=False)
        self.table_display.seat_clicked.connect(self._seat_clicked)
        root.addWidget(self.table_display, 1)

        note = QLabel(
            "PokerMeow starts a hand automatically when two seated players are present."
        )
        note.setObjectName("muted")
        root.addWidget(note)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start Game — automatic")
        self.start_button.setEnabled(False)
        self.leave_button = QPushButton("Leave")
        controls.addWidget(self.start_button)
        controls.addStretch()
        controls.addWidget(self.leave_button)
        root.addLayout(controls)
        self.leave_button.clicked.connect(self.leave_requested)

    def configure(self, is_host):
        self.start_button.setVisible(is_host)

    def set_status(self, text):
        self.status.setText(text)

    def set_leave_pending(self, pending):
        self.leave_button.setEnabled(True)
        self.leave_button.setText("Cancel Leave" if pending else "Leave")

    def set_table_id(self, table_id):
        self.table_id.setText(f"Table {table_id or '—'}")

    def update_table(self, table, username=""):
        if not table:
            return
        self.set_table_id(table.get("table_id", ""))
        self.table_display.update_lobby(table, username)

    def request_seat_selection(self, table, available_seats):
        self.update_table(table)
        self._seat_selection_active = True
        self.table_display.set_pickable_seats(available_seats)
        self.set_status("Choose a seat by clicking it.")

    def clear_seat_selection(self):
        self._seat_selection_active = False
        self.table_display.clear_pickable_seats()

    def _seat_clicked(self, seat_number):
        if self._seat_selection_active:
            self.seat_selected.emit(seat_number)


class TableView(QWidget):
    action_requested = Signal(str, float)
    leave_requested = Signal()

    ACTIONS = ("fold", "check", "call", "bet", "raise", "all_in")

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QGridLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setHorizontalSpacing(8)
        root.setVerticalSpacing(6)

        top = QHBoxLayout()
        self.table_name = QLabel("Poker table")
        self.table_name.setObjectName("sectionTitle")
        self.turn = QLabel("Waiting for action")
        top.addWidget(self.table_name)
        top.addStretch()
        top.addWidget(self.turn)
        root.addLayout(top, 0, 0, 1, 2)

        self.table_display = PokerTableDisplay(show_game_details=True)
        root.addWidget(self.table_display, 1, 0)

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
        root.addLayout(side, 1, 1)

        actions = QGroupBox("Betting controls")
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setSpacing(6)

        self.sizing_panel = QWidget()
        sizing_layout = QHBoxLayout(self.sizing_panel)
        sizing_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_size_button = QPushButton("Custom")
        self.custom_size_button.clicked.connect(self._show_custom_amount)
        sizing_layout.addWidget(self.custom_size_button)
        self.preset_buttons = {}
        for label, fraction in (
            ("1/3", Decimal(1) / Decimal(3)),
            ("1/2", Decimal(1) / Decimal(2)),
            ("3/4", Decimal(3) / Decimal(4)),
            ("Pot", Decimal(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, selected=fraction: self._send_preset(
                    selected
                )
            )
            self.preset_buttons[label] = button
            sizing_layout.addWidget(button)
        self.cancel_size_button = QPushButton("Cancel")
        self.cancel_size_button.clicked.connect(self._close_sizing)
        sizing_layout.addWidget(self.cancel_size_button)
        self.sizing_panel.setVisible(False)
        actions_layout.addWidget(self.sizing_panel)

        self.custom_amount_panel = QWidget()
        custom_layout = QHBoxLayout(self.custom_amount_panel)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_amount_label = QLabel("Amount")
        self.custom_amount = QDoubleSpinBox()
        self.custom_amount.setRange(0, 1_000_000_000)
        self.custom_amount.setDecimals(2)
        self.custom_submit = QPushButton("Submit")
        self.custom_submit.setObjectName("primary")
        self.custom_submit.clicked.connect(self._send_custom_amount)
        self.custom_cancel_button = QPushButton("Cancel")
        self.custom_cancel_button.clicked.connect(self._close_sizing)
        custom_layout.addWidget(self.custom_amount_label)
        custom_layout.addWidget(self.custom_amount)
        custom_layout.addWidget(self.custom_submit)
        custom_layout.addWidget(self.custom_cancel_button)
        self.custom_amount_panel.setVisible(False)
        actions_layout.addWidget(self.custom_amount_panel)

        base_actions = QHBoxLayout()
        self.action_buttons = {}
        for action in self.ACTIONS:
            button = QPushButton(action.replace("_", " ").title())
            button.setEnabled(False)
            if action in {"bet", "raise"}:
                button.clicked.connect(
                    lambda checked=False, selected=action: self._open_sizing(
                        selected
                    )
                )
            else:
                button.clicked.connect(
                    lambda checked=False, selected=action: self._send_action(
                        selected
                    )
                )
            self.action_buttons[action] = button
            base_actions.addWidget(button)
        self.leave_button = QPushButton("Leave")
        self.leave_button.clicked.connect(self.leave_requested)
        base_actions.addWidget(self.leave_button)
        actions_layout.addLayout(base_actions)
        root.addWidget(actions, 2, 0, 1, 2)
        root.setColumnStretch(0, 3)
        root.setColumnStretch(1, 2)

        self.current_table_id = None
        self.current_pot = Decimal(0)
        self.own_current_bet = Decimal(0)
        self.own_stack = Decimal(0)
        self.action_request = {}
        self.sizing_action = None
        self.sizing_amounts = {}

    def update_state(self, state, table, username):
        self.current_pot = self._decimal(state.get("pot", 0))
        if table:
            self.set_table_context(table.get("table_id"))
            self.table_name.setText(
                f"{table.get('game', 'Poker')} · {table.get('table_id', '')}"
            )
        for name, player in state.get("players", {}).items():
            if name == username:
                self.own_current_bet = self._decimal(player.get("current_bet", 0))
                self.own_stack = self._decimal(player.get("stack", 0))
                break
        self.table_display.update_game(state, table, username)

    def show_showdown_hands(self, hands):
        self.table_display.show_showdown_hands(hands)

    def spotlight_showdown(self, cards, hand_name=""):
        self.table_display.spotlight_showdown(cards, hand_name)

    def show_payouts(self, payouts):
        self.table_display.show_payouts(payouts)

    def set_legal_actions(self, request):
        self._close_sizing()
        self.action_request = dict(request)
        legal = set(request.get("legal_actions", []))
        for action, button in self.action_buttons.items():
            button.setEnabled(action in legal)
        to_call = request.get("to_call", 0)
        call_text = display_amount(to_call)
        self.action_buttons["call"].setText(
            f"Call {call_text}" if "call" in legal else "Call"
        )
        self.turn.setText(f"Your turn \u00b7 call {call_text}")
        self.turn.setObjectName("turnActive")
        self.turn.style().unpolish(self.turn)
        self.turn.style().polish(self.turn)

    def clear_legal_actions(self):
        for button in self.action_buttons.values():
            button.setEnabled(False)
        self.action_buttons["call"].setText("Call")
        self.action_request = {}
        self._close_sizing()
        self.turn.setText("Waiting for another player")

    def append_history(self, text):
        if text:
            self.history.append(str(text))

    def set_hand_history(self, history):
        self.history.clear()
        for item in history:
            self.append_history(item)

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
        self.set_leave_pending(False)
        self.clear_legal_actions()

    def set_leave_pending(self, pending):
        self.leave_button.setEnabled(True)
        self.leave_button.setText("Cancel Leave" if pending else "Leave")

    def append_chat(self, text):
        if text:
            self.chat.append(str(text))

    def _send_action(self, action, amount=0):
        self.action_requested.emit(action, amount)
        self.clear_legal_actions()
        suffix = f" {amount:g}" if action in {"bet", "raise"} else ""
        self.append_history(f"You: {action}{suffix}")

    def _open_sizing(self, action):
        if action not in self.action_request.get("legal_actions", []):
            return
        self.sizing_action = action
        self.sizing_amounts = {}
        title = action.title()
        self.custom_size_button.setText(f"{title} Custom")
        for label, fraction in (
            ("1/3", Decimal(1) / Decimal(3)),
            ("1/2", Decimal(1) / Decimal(2)),
            ("3/4", Decimal(3) / Decimal(4)),
            ("Pot", Decimal(1)),
        ):
            amount = self._preset_amount(action, fraction)
            self.sizing_amounts[label] = amount
            self.preset_buttons[label].setText(
                f"{title} {label} ({display_amount(amount)})"
            )
        self.custom_amount_panel.setVisible(False)
        self.sizing_panel.setVisible(True)

    def _show_custom_amount(self):
        if self.sizing_action is None:
            return
        minimum, maximum = self._amount_bounds(self.sizing_action)
        self.custom_amount_label.setText(
            f"{self.sizing_action.title()} amount"
        )
        self.custom_submit.setText(self.sizing_action.title())
        self.custom_amount.setMinimum(float(minimum))
        self.custom_amount.setMaximum(float(maximum))
        self.custom_amount.setValue(float(minimum))
        self.sizing_panel.setVisible(False)
        self.custom_amount_panel.setVisible(True)
        self.custom_amount.setFocus()

    def _send_preset(self, fraction):
        if self.sizing_action is None:
            return
        amount = self._preset_amount(self.sizing_action, fraction)
        self._send_action(self.sizing_action, float(amount))

    def _send_custom_amount(self):
        if self.sizing_action is None:
            return
        self._send_action(
            self.sizing_action,
            self.custom_amount.value(),
        )

    def _close_sizing(self):
        self.sizing_panel.setVisible(False)
        self.custom_amount_panel.setVisible(False)
        self.sizing_action = None
        self.sizing_amounts = {}

    def _preset_amount(self, action, fraction):
        to_call = self._decimal(self.action_request.get("to_call", 0))
        if action == "bet":
            raw_amount = self.current_pot * fraction
        else:
            current_table_bet = self.own_current_bet + to_call
            pot_after_call = self.current_pot + to_call
            raw_amount = current_table_bet + pot_after_call * fraction
        rounded = raw_amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        minimum, maximum = self._amount_bounds(action)
        return max(minimum, min(rounded, maximum))

    def _amount_bounds(self, action):
        if action == "bet":
            minimum = self._decimal(
                self.action_request.get("min_raise", 0)
            )
            maximum_value = self.action_request.get("max_bet")
        else:
            minimum = self._decimal(
                self.action_request.get(
                    "min_raise_to",
                    self.action_request.get("min_raise", 0),
                )
            )
            maximum_value = self.action_request.get("max_raise_to")
        if maximum_value is None:
            maximum = self.own_current_bet + self.own_stack
        else:
            maximum = self._decimal(maximum_value)
        maximum = max(minimum, maximum)
        return minimum, maximum

    @staticmethod
    def _decimal(value):
        try:
            amount = Decimal(str(value))
            if amount.is_finite():
                return amount
        except (InvalidOperation, TypeError, ValueError):
            pass
        return Decimal(0)

class PokerStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.menu = MainMenuView()
        self.lobby = LobbyView()
        self.table = TableView()
        self.addWidget(self.menu)
        self.addWidget(self.lobby)
        self.addWidget(self.table)
