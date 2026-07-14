from collections import defaultdict
from decimal import Decimal, InvalidOperation
import threading

from .networking import JsonConnection


class ClientController:
    """Presentation-neutral adapter between a UI and PokerMeow's protocol."""

    def __init__(self, connection_factory=JsonConnection):
        self._listeners = defaultdict(list)
        self._listener_lock = threading.Lock()
        self._connection_factory = connection_factory
        self._connection = None
        self.username = ""
        self.mode = "join"
        self.table_id = ""
        self.table_config = {}
        self.buy_in = Decimal("1000")
        self.is_host = False
        self.latest_state = None
        self.latest_table = None
        self._waiting_for_new_name = False
        self._waiting_for_table_id = False
        self._name_error = ""
        self._table_id_error = ""

    @property
    def connected(self):
        return self._connection is not None and self._connection.connected

    def subscribe(self, event, callback):
        with self._listener_lock:
            self._listeners[event].append(callback)

    def connect(
        self,
        host,
        port,
        username,
        mode,
        table_id="",
        buy_in="1000",
        table_config=None,
    ):
        if self.connected:
            raise RuntimeError("Already connected")
        if not str(username).strip():
            raise ValueError("Username is required")
        if mode not in {"create", "join"}:
            raise ValueError("Mode must be create or join")
        if mode == "join" and not str(table_id).strip():
            raise ValueError("Table ID is required when joining")

        try:
            parsed_buy_in = Decimal(str(buy_in))
        except InvalidOperation as error:
            raise ValueError("Buy-in must be a number") from error
        if not parsed_buy_in.is_finite() or parsed_buy_in <= 0:
            raise ValueError("Buy-in must be greater than zero")

        self.username = str(username).strip()
        self.mode = mode
        self.is_host = mode == "create"
        self.table_id = str(table_id).strip().upper()
        self.buy_in = parsed_buy_in
        self.table_config = table_config or {
            "game": "nlh",
            "max_seats": 6,
            "big_blind": "2",
        }
        self.latest_state = None
        self.latest_table = None
        self._waiting_for_new_name = False
        self._waiting_for_table_id = False
        self._name_error = ""
        self._table_id_error = ""

        connection = self._connection_factory(
            self._handle_message,
            self._handle_disconnect,
        )
        self._connection = connection
        self._emit("status", f"Connecting to {host}:{port}…")
        try:
            connection.connect(host, int(port))
        except Exception:
            connection.close()
            self._connection = None
            raise
        self._emit("connected", {"host": host, "port": int(port)})

    def disconnect(self):
        connection = self._connection
        self._connection = None
        if connection is not None:
            connection.close()
        self._emit("disconnected", "Disconnected.")

    def choose_seat(self, seat):
        self._send({"type": "seat_choice", "seat": int(seat)})

    def submit_action(self, action, amount=0):
        action = str(action).lower()
        if action not in {"fold", "check", "call", "bet", "raise", "all_in"}:
            raise ValueError(f"Unknown action: {action}")
        self._send({"type": "action", "action": action, "amount": amount})
        self._emit("action_sent", {"action": action, "amount": amount})

    def submit_continue(self, wants_to_continue):
        self._send({"type": "continue", "continue": bool(wants_to_continue)})

    def request_leave(self):
        self._send({"type": "leave_table"})

    def cancel_leave(self):
        self._send({"type": "cancel_leave"})

    def submit_rebuy(self, amount=None):
        if amount is None:
            self._send({"type": "rebuy", "rebuy": False})
            return
        try:
            parsed_amount = Decimal(str(amount))
        except InvalidOperation as error:
            raise ValueError("Rebuy amount must be a number") from error
        if not parsed_amount.is_finite() or parsed_amount <= 0:
            raise ValueError("Rebuy amount must be greater than zero")
        self._send(
            {
                "type": "rebuy",
                "rebuy": True,
                "amount": parsed_amount,
            }
        )

    def submit_name(self, name):
        name = str(name).strip()
        if not name:
            raise ValueError("Username is required")
        self.username = name
        self._waiting_for_new_name = False
        self._name_error = ""
        self._send({"type": "join", "name": name})

    def submit_table_id(self, table_id):
        table_id = str(table_id).strip().upper()
        if not table_id:
            raise ValueError("Table ID is required")
        self.table_id = table_id
        self._waiting_for_table_id = False
        self._table_id_error = ""
        self._send({"type": "table_id", "table_id": table_id})

    def submit_allocator_allocation(self, top, bottom, hand):
        self._send(
            {
                "type": "allocator_allocation",
                "top": list(top),
                "bottom": list(bottom),
                "hand": list(hand),
            }
        )

    def _send(self, message):
        if self._connection is None:
            raise ConnectionError("Not connected")
        try:
            self._connection.send(message)
        except (ConnectionError, OSError) as error:
            self._emit("error", str(error))

    def _handle_message(self, message):
        message_type = message.get("type")

        if message_type == "welcome":
            self._emit("status", message.get("message", "Connected."))
        elif message_type == "request_lobby_action":
            self._send({"type": "lobby_action", "action": self.mode})
            self._emit("lobby_entered", {"is_host": self.is_host})
        elif message_type == "request_table_config":
            payload = {"type": "table_config", **self.table_config}
            self._send(payload)
        elif message_type == "table_created":
            self.table_id = message.get("table_id", "")
            self._emit("table_created", dict(message))
        elif message_type == "request_table_id":
            if self._waiting_for_table_id:
                self._emit(
                    "table_id_required",
                    self._table_id_error or "Enter another table ID.",
                )
            else:
                self._send({"type": "table_id", "table_id": self.table_id})
        elif message_type == "request_name":
            if self._waiting_for_new_name:
                self._emit(
                    "name_required",
                    self._name_error or "Enter another username.",
                )
            else:
                self._send({"type": "join", "name": self.username})
        elif message_type == "name_taken":
            self._waiting_for_new_name = True
            self._name_error = message.get("message", "Name is taken.")
        elif message_type == "joined":
            self.username = message.get("name", self.username)
            self._emit("joined", dict(message))
        elif message_type == "request_buy_in":
            self._send({"type": "buy_in", "amount": self.buy_in})
        elif message_type == "request_seat":
            self.latest_table = message.get("table")
            if self.latest_table:
                self._emit("table", self.latest_table)
            self._emit("seat_required", dict(message))
        elif message_type == "table":
            self.latest_table = message.get("table")
            if self.latest_table:
                self._emit("table", self.latest_table)
        elif message_type in {"seated", "reserved", "waiting"}:
            self._update_own_lobby_seat(message_type, message)
            self._emit("lobby_status", dict(message))
        elif message_type == "state":
            self.latest_state = message.get("state", {})
            self.latest_table = message.get("table")
            self._emit("state", dict(message))
        elif message_type == "request_action":
            self._emit("action_required", dict(message))
        elif message_type == "hand_history":
            self._emit("hand_history", list(message.get("history", [])))
        elif message_type == "request_allocator_allocation":
            self._emit("allocator_required", dict(message))
        elif message_type == "showdown":
            self._emit("showdown", dict(message))
        elif message_type == "request_continue":
            # Compatibility with older servers: the GUI always continues.
            self.submit_continue(True)
        elif message_type == "request_rebuy":
            self._emit("rebuy_required", dict(message))
        elif message_type == "rebought":
            try:
                self.buy_in = Decimal(str(message.get("amount", self.buy_in)))
            except InvalidOperation:
                pass
            self._emit("rebought", dict(message))
        elif message_type == "leave_scheduled":
            self._emit("leave_scheduled", message.get("message", ""))
        elif message_type == "leave_cancelled":
            self._emit("leave_cancelled", message.get("message", ""))
        elif message_type == "left_table":
            self._emit("left_table", message.get("message", "You left the table."))
        elif message_type == "disconnect_timer":
            self._emit("disconnect_timer", dict(message))
        elif message_type == "message":
            self._emit("message", message.get("message", ""))
        elif message_type == "table_not_found":
            self._waiting_for_table_id = True
            self._table_id_error = message.get("message", "Table not found.")
        elif message_type == "error":
            self._emit("error", message.get("message", "Server error"))
        elif message_type == "session_over":
            self._emit("session_over", message.get("message", "Session ended."))
        else:
            self._emit("unknown_message", dict(message))

    def _handle_disconnect(self, reason):
        self._connection = None
        self._emit("disconnected", reason)

    def _update_own_lobby_seat(self, status, message):
        if not self.latest_table or status == "waiting":
            return
        seat_number = message.get("seat")
        for seat in self.latest_table.get("seats", []):
            if seat.get("seat") != seat_number:
                continue
            seat.update(
                {
                    "status": status,
                    "player": self.username,
                    "stack": str(self.buy_in),
                }
            )
            self._emit("table", self.latest_table)
            return

    def _emit(self, event, payload):
        with self._listener_lock:
            callbacks = list(self._listeners.get(event, ()))
            callbacks += list(self._listeners.get("*", ()))
        for callback in callbacks:
            callback(event, payload)
