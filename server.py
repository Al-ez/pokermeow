import argparse
import select
import socket
import random
import string
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from allocator import AllocatorGame
from network_protocol import recv_json, send_json, visible_state_for
from nlh import HandEvaluator, NoLimitHoldemGame
from plo import PotLimitOmahaGame


def local_ipv4_addresses():
    addresses = []
    try:
        hostname = socket.gethostname()
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = result[4][0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
    except OSError:
        pass

    return addresses


def parse_money(value, field_name, allow_zero=False):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RuntimeError(f"{field_name} must be a valid number")

    if not amount.is_finite():
        raise RuntimeError(f"{field_name} must be a valid number")

    if amount < 0 or (amount == 0 and not allow_zero):
        raise RuntimeError(f"{field_name} must be greater than zero")

    return amount


@dataclass
class Seat:
    client: object
    stack: int
    reserved: bool = False


class Client:
    def __init__(self, socket_obj, address, shutdown_event=None):
        self.socket = socket_obj
        self.address = address
        self.file = socket_obj.makefile("rw", encoding="utf-8", newline="\n")
        self.name = None
        self.buy_in = None
        self.connected = True
        self.shutdown_event = shutdown_event or threading.Event()

    def send(self, message):
        if not self.connected:
            raise ConnectionError("Client is disconnected")

        try:
            send_json(self.file, message)
        except OSError as error:
            self.connected = False
            raise ConnectionError("Client is disconnected") from error

    def recv(self):
        if not self.connected:
            return None

        while not self.shutdown_event.is_set():
            try:
                readable, _, _ = select.select([self.socket], [], [], 1)
            except (OSError, ValueError):
                self.connected = False
                return None

            if not readable:
                continue

            try:
                message = recv_json(self.file)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                self.connected = False
                return None

            if message is None:
                self.connected = False

            return message

        self.connected = False
        return None

    def force_close(self):
        self.connected = False
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.file.close()
        except OSError:
            pass
        try:
            self.socket.close()
        except OSError:
            pass

    def set_timeout(self, timeout):
        self.socket.settimeout(timeout)

    def close(self):
        self.connected = False
        try:
            self.file.close()
        except OSError:
            pass
        try:
            self.socket.close()
        except OSError:
            pass


class Table:
    TABLE_SEATS = 10

    def __init__(self, max_seats):
        self.max_seats = max_seats
        self.seats = [None for _ in range(max_seats)]
        self.waiting_list = []
        self.hand_in_progress = False
        self.lock = threading.Lock()

    def available_seats(self):
        with self.lock:
            return [
                index + 1
                for index, seat in enumerate(self.seats)
                if seat is None
            ]

    def reserve_or_seat_client(self, client, seat_number):
        index = seat_number - 1
        with self.lock:
            if index < 0 or index >= self.max_seats:
                return "invalid", None

            if self.seats[index] is not None:
                return "taken", None

            reserved = self.hand_in_progress
            self.seats[index] = Seat(client, client.buy_in, reserved=reserved)

            if reserved:
                return "reserved", seat_number

            return "seated", seat_number

    def add_to_waiting_list(self, client):
        with self.lock:
            self.waiting_list.append(client)
            return "waiting", len(self.waiting_list)

    def activate_reserved_seats(self):
        activated = []
        with self.lock:
            for index, seat in enumerate(self.seats):
                if seat is not None and seat.reserved:
                    seat.reserved = False
                    activated.append((seat.client, index + 1))

        for client, seat_number in activated:
            client.send(
                {
                    "type": "seated",
                    "seat": seat_number,
                    "message": f"You are seated in seat {seat_number}.",
                }
            )

        return activated

    def pop_next_waiting_client(self):
        with self.lock:
            if not self.waiting_list:
                return None

            if self._first_open_seat() is None:
                return None

            return self.waiting_list.pop(0)

    def seated_clients(self):
        with self.lock:
            return [
                seat.client
                for seat in self.seats
                if seat is not None and not seat.reserved
            ]

    def seated_player_stacks(self):
        with self.lock:
            return {
                seat.client.name: seat.stack
                for seat in self.seats
                if seat is not None and not seat.reserved
            }

    def client_by_name(self, name):
        target_name = name.lower()
        with self.lock:
            for seat in self.seats:
                if seat is not None and seat.client.name.lower() == target_name:
                    return seat.client

        return None

    def disconnected_client_by_name(self, name):
        target_name = name.lower()
        with self.lock:
            for seat in self.seats:
                if (
                    seat is not None
                    and seat.client.name.lower() == target_name
                    and not seat.client.connected
                ):
                    return seat.client

        return None

    def replace_client(self, name, new_client):
        target_name = name.lower()
        with self.lock:
            for seat in self.seats:
                if seat is not None and seat.client.name.lower() == target_name:
                    old_client = seat.client
                    new_client.name = old_client.name
                    new_client.buy_in = old_client.buy_in
                    new_client.connected = True
                    seat.client = new_client
                    return True

        return False

    def active_names(self):
        with self.lock:
            names = {
                seat.client.name.lower()
                for seat in self.seats
                if seat is not None
            }
            names.update(
                client.name.lower()
                for client in self.waiting_list
                if client.name
            )

        return names

    def table_status(self):
        with self.lock:
            seats = []
            for index in range(self.TABLE_SEATS):
                if index >= self.max_seats:
                    seats.append(
                        {
                            "seat": index + 1,
                            "status": "closed",
                            "player": None,
                            "stack": None,
                        }
                    )
                    continue

                seat = self.seats[index]
                if seat is None:
                    seats.append(
                        {
                            "seat": index + 1,
                            "status": "open",
                            "player": None,
                            "stack": None,
                        }
                    )
                else:
                    seats.append(
                        {
                            "seat": index + 1,
                            "status": "reserved" if seat.reserved else "seated",
                            "player": seat.client.name,
                            "stack": seat.stack,
                        }
                    )

            return {
                "max_seats": self.max_seats,
                "seats": seats,
                "waiting": [client.name for client in self.waiting_list],
            }

    def update_stacks(self, game):
        stacks = {
            player.name: player.stack
            for player in game.players
        }

        busted = []
        with self.lock:
            for index, seat in enumerate(self.seats):
                if seat is None:
                    continue

                if seat.client.name in stacks:
                    seat.stack = stacks[seat.client.name]

                if seat.stack <= 0:
                    busted.append(seat.client)
                    self.seats[index] = None

        for client in busted:
            client.send(
                {
                    "type": "session_over",
                    "message": "You are out of chips. Your seat is now open.",
                }
            )

    def remove_client(self, client):
        removed = False
        with self.lock:
            for index, seat in enumerate(self.seats):
                if seat is not None and seat.client is client:
                    self.seats[index] = None
                    removed = True
                    break

            self.waiting_list = [
                waiting_client
                for waiting_client in self.waiting_list
                if waiting_client is not client
            ]

        return removed

    def mark_hand_started(self):
        with self.lock:
            self.hand_in_progress = True

    def mark_hand_finished(self):
        with self.lock:
            self.hand_in_progress = False

    def waiting_count(self):
        with self.lock:
            return len(self.waiting_list)

    def _first_open_seat(self):
        for index, seat in enumerate(self.seats):
            if seat is None:
                return index

        return None


class PokerTableSession:
    def __init__(
        self,
        table_id,
        game_class,
        game_name,
        small_blind,
        big_blind,
        max_seats,
        bomb_pot_ante=0,
        shutdown_event=None,
    ):
        self.table_id = table_id
        self.game_class = game_class
        self.game_name = game_name
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.bomb_pot_ante = bomb_pot_ante
        self.table = Table(max_seats)
        self.all_clients = []
        self.all_clients_lock = threading.Lock()
        self.pending_names = set()
        self.pending_names_lock = threading.Lock()
        self.game = None
        self.dealer_index = 0
        self.shutdown_event = shutdown_event or threading.Event()

    def run(self):
        print(f"Table {self.table_id} started.")
        print(f"Game: {self.game_name}")
        if self.game_class is AllocatorGame:
            print(f"Bomb pot ante: {self.bomb_pot_ante}")
        else:
            print(f"Blinds: {self.small_blind}/{self.big_blind}")
        print(f"Table has {self.table.max_seats} seats.")

        while not self.shutdown_event.is_set():
            self._activate_reserved_and_offer_waiting_list()

            if len(self.table.seated_clients()) < 2:
                print("Waiting for at least 2 seated players...")
                self.shutdown_event.wait(2)
                continue

            self._play_hand()

    def stop(self):
        self.shutdown_event.set()
        with self.all_clients_lock:
            clients = list(self.all_clients)

        for client in clients:
            client.force_close()

    def add_client_to_table(self, client, address):
        self._request_table_name(client)

        disconnected_client = self.table.disconnected_client_by_name(client.name)
        if disconnected_client is not None:
            if not self.table.replace_client(client.name, client):
                raise RuntimeError("Unable to reconnect player")

            with self.all_clients_lock:
                self.all_clients.append(client)

            print(f"{client.name} reconnected to table {self.table_id}.")
            client.send({"type": "joined", "name": client.name})
            client.send(
                {
                    "type": "message",
                    "message": f"Reconnected to table {self.table_id}.",
                }
            )
            return

        client.name = self._claim_unique_name(client, client.name)
        client.send({"type": "joined", "name": client.name})

        try:
            self._request_buy_in(client)

            with self.all_clients_lock:
                self.all_clients.append(client)

            self._place_new_client(client, address)
        finally:
            self._release_pending_name(client.name)

    def _table_status(self):
        status = self.table.table_status()
        status["table_id"] = self.table_id
        status["game"] = self.game_name
        return status

    def _request_table_name(self, client):
        client.send({"type": "request_name"})
        message = client.recv()
        if not message or message.get("type") != "join":
            raise RuntimeError("Client disconnected before choosing a name")

        name = message.get("name", "").strip()
        if not name:
            name = "Player"

        client.name = name

    def _request_buy_in(self, client):
        client.send({"type": "request_buy_in"})
        buy_in_message = client.recv()
        if not buy_in_message or buy_in_message.get("type") != "buy_in":
            raise RuntimeError("Client disconnected before choosing a buy-in")

        try:
            buy_in = parse_money(buy_in_message.get("amount"), "Buy-in")
        except (TypeError, ValueError):
            raise RuntimeError("Invalid buy-in amount")

        if buy_in <= 0:
            raise RuntimeError("Buy-in must be greater than zero")

        client.buy_in = buy_in

    def _accept_clients(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen()

            while True:
                socket_obj, address = server_socket.accept()
                client = Client(socket_obj, address, self.shutdown_event)
                thread = threading.Thread(
                    target=self._handle_new_client,
                    args=(client, address),
                    daemon=True,
                )
                thread.start()

    def _handle_new_client(self, client, address):
        try:
            reconnected = self._welcome_client(client)
        except Exception:
            self._release_pending_name(client.name)
            client.close()
            return

        with self.all_clients_lock:
            self.all_clients.append(client)

        if reconnected:
            print(f"{client.name} reconnected from {address[0]}:{address[1]}.")
            client.send(
                {
                    "type": "message",
                    "message": "Reconnected to your seat.",
                }
            )
        else:
            self._place_new_client(client, address)

        self._release_pending_name(client.name)

    def _welcome_client(self, client):
        client.send({"type": "welcome", "message": "Connected to PokerMeow server."})
        client.send({"type": "request_name"})
        message = client.recv()
        if not message or message.get("type") != "join":
            raise RuntimeError("Client disconnected before joining")

        name = message.get("name", "").strip()
        if not name:
            name = "Player"

        disconnected_client = self.table.disconnected_client_by_name(name)
        if disconnected_client is not None:
            if not self.table.replace_client(name, client):
                raise RuntimeError("Unable to reconnect player")

            client.send({"type": "joined", "name": client.name})
            return True

        name = self._claim_unique_name(client, name)

        client.name = name
        client.send({"type": "joined", "name": client.name})

        client.send({"type": "request_buy_in"})
        buy_in_message = client.recv()
        if not buy_in_message or buy_in_message.get("type") != "buy_in":
            raise RuntimeError("Client disconnected before choosing a buy-in")

        try:
            buy_in = parse_money(buy_in_message.get("amount"), "Buy-in")
        except (TypeError, ValueError):
            raise RuntimeError("Invalid buy-in amount")

        if buy_in <= 0:
            raise RuntimeError("Buy-in must be greater than zero")

        client.buy_in = buy_in
        return False

    def _release_pending_name(self, name):
        if not name:
            return

        with self.pending_names_lock:
            self.pending_names.discard(name.lower())

    def _claim_unique_name(self, client, name):
        while True:
            with self.pending_names_lock:
                existing_names = self.table.active_names() | self.pending_names
                if name.lower() not in existing_names:
                    self.pending_names.add(name.lower())
                    return name

            client.send(
                {
                    "type": "name_taken",
                    "message": f"The name {name!r} is already taken. Choose another name.",
                }
            )
            client.send({"type": "request_name"})
            message = client.recv()
            if not message or message.get("type") != "join":
                raise RuntimeError("Client disconnected before choosing a unique name")

            name = message.get("name", "").strip()
            if not name:
                name = "Player"

    def _place_new_client(self, client, address):
        if not self.table.available_seats():
            status, position = self.table.add_to_waiting_list(client)
            print(
                f"{client.name} joined from {address[0]}:{address[1]} "
                f"and is waiting at queue position {position}."
            )
            client.send(
                {
                    "type": "waiting",
                    "position": position,
                    "message": (
                        "All seats are taken or reserved. "
                        f"You are waiting at queue position {position}."
                    ),
                }
            )
            return

        seat_number = self._request_seat_choice(client)
        status, seat_number = self.table.reserve_or_seat_client(client, seat_number)

        while status in {"invalid", "taken"}:
            client.send(
                {
                    "type": "error",
                    "message": "That seat is not available. Choose another seat.",
                }
            )
            seat_number = self._request_seat_choice(client)
            status, seat_number = self.table.reserve_or_seat_client(client, seat_number)

        if status == "reserved":
            print(
                f"{client.name} joined from {address[0]}:{address[1]} "
                f"and reserved seat {seat_number}."
            )
            client.send(
                {
                    "type": "reserved",
                    "seat": seat_number,
                    "message": (
                        f"You reserved seat {seat_number}. "
                        "You will join after the current hand."
                    ),
                }
            )
        else:
            print(
                f"{client.name} joined from {address[0]}:{address[1]} "
                f"and sat in seat {seat_number}."
            )
            client.send(
                {
                    "type": "seated",
                    "seat": seat_number,
                    "message": f"You are seated in seat {seat_number}.",
                }
            )

    def _request_seat_choice(self, client):
        while True:
            available_seats = self.table.available_seats()
            client.send(
                {
                    "type": "request_seat",
                    "available_seats": available_seats,
                    "table": self._table_status(),
                }
            )
            message = client.recv()
            if not message or message.get("type") != "seat_choice":
                raise RuntimeError(f"{client.name} disconnected before choosing a seat")

            try:
                seat_number = int(message.get("seat"))
            except (TypeError, ValueError):
                client.send({"type": "error", "message": "Seat must be a number."})
                continue

            if seat_number not in available_seats:
                client.send(
                    {
                        "type": "error",
                        "message": "That seat is not available.",
                    }
                )
                continue

            return seat_number

    def _activate_reserved_and_offer_waiting_list(self):
        self.table.activate_reserved_seats()

        while self.table.available_seats():
            client = self.table.pop_next_waiting_client()
            if client is None:
                return

            client.send(
                {
                    "type": "message",
                    "message": "A seat is now available.",
                }
            )
            try:
                seat_number = self._request_seat_choice(client)
                status, seat_number = self.table.reserve_or_seat_client(
                    client,
                    seat_number,
                )
            except Exception:
                client.close()
                continue

            if status == "seated":
                client.send(
                    {
                        "type": "seated",
                        "seat": seat_number,
                        "message": f"You are seated in seat {seat_number}.",
                    }
                )

    def _play_hand(self):
        if self.shutdown_event.is_set():
            return

        self.table.mark_hand_started()
        seated_clients = self.table.seated_clients()
        player_stacks = self.table.seated_player_stacks()

        if self.game_class is AllocatorGame:
            self.game = self.game_class(
                player_stacks,
                small_blind=1,
                big_blind=2,
                shuffle=True,
                bomb_pot_ante=self.bomb_pot_ante,
            )
        else:
            self.game = self.game_class(
                player_stacks,
                small_blind=self.small_blind,
                big_blind=self.big_blind,
                shuffle=True,
            )
        self.dealer_index %= len(self.game.players)
        self.game.dealer_index = self.dealer_index

        try:
            self.game.start_hand()
            self._broadcast_to(seated_clients, {"type": "message", "message": "New hand started."})
            self._send_states_to(seated_clients)

            if self.game_class is not AllocatorGame:
                self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and self._should_skip_to_showdown():
                self._deal_remaining_board(seated_clients)
            elif len(self.game.active_players()) > 1:
                self.game.deal_flop()
                self._broadcast_to(
                    seated_clients,
                    {
                        "type": "message",
                        "message": "Flops dealt." if self.game_class is AllocatorGame else "Flop dealt.",
                    },
                )
                self._send_states_to(seated_clients)
                self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and len(self.game.board) == 3:
                if self._should_skip_to_showdown():
                    self._deal_remaining_board(seated_clients)
                else:
                    self.game.deal_turn()
                    self._broadcast_to(
                        seated_clients,
                        {
                            "type": "message",
                            "message": "Turns dealt." if self.game_class is AllocatorGame else "Turn dealt.",
                        },
                    )
                    self._send_states_to(seated_clients)
                    self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and len(self.game.board) == 4:
                if self._should_skip_to_showdown():
                    self._deal_remaining_board(seated_clients)
                else:
                    self.game.deal_river()
                    self._broadcast_to(
                        seated_clients,
                        {
                            "type": "message",
                            "message": "Rivers dealt." if self.game_class is AllocatorGame else "River dealt.",
                        },
                    )
                    self._send_states_to(seated_clients)
                    self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and len(self.game.board) < 5:
                self._deal_remaining_board(seated_clients)

            if self.game_class is AllocatorGame and len(self.game.active_players()) > 1:
                self._request_allocator_allocations(seated_clients)

            result = self.game.showdown()
            if result.hand_name == "uncontested":
                winner_hand_names = {
                    winner: result.hand_name
                    for winner in result.winners
                }
                allocator_details = None
            elif self.game_class is AllocatorGame:
                scores = self.game.calculate_scores()
                winner_hand_names = {
                    winner: f"{scores[winner].total} points"
                    for winner in result.winners
                }
                allocator_details = self._allocator_showdown_details()
            elif len(self.game.board) == 5:
                winner_hand_names = {
                    player.name: HandEvaluator.best_hand(player.hand + self.game.board)[3]
                    for player in self.game.players
                    if player.name in result.winners and not player.folded
                }
                allocator_details = None
            else:
                winner_hand_names = {
                    winner: result.hand_name
                    for winner in result.winners
                }
                allocator_details = None

            revealed_hands = []
            if result.hand_name != "uncontested":
                revealed_hands = [
                    {
                        "player": player.name,
                        "hand": [str(card) for card in player.hand],
                    }
                    for player in self.game.players
                    if not player.folded
                ]

            self._send_states_to(seated_clients)
            self._broadcast_to(
                seated_clients,
                {
                    "type": "showdown",
                    "winners": result.winners,
                    "hand_name": result.hand_name,
                    "winner_hand_names": winner_hand_names,
                    "board": [str(card) for card in self.game.board],
                    "top_board": (
                        [str(card) for card in self.game.top_board]
                        if hasattr(self.game, "top_board")
                        else None
                    ),
                    "bottom_board": (
                        [str(card) for card in self.game.bottom_board]
                        if hasattr(self.game, "bottom_board")
                        else None
                    ),
                    "allocator_details": allocator_details,
                    "amount_won": result.amount_won,
                    "hands": revealed_hands,
                },
            )

            self.table.update_stacks(self.game)
            self._ask_next_hand(seated_clients)
            self.dealer_index = (self.game.dealer_index + 1) % len(self.game.players)
        finally:
            self.table.mark_hand_finished()
            if not self.shutdown_event.is_set():
                self._activate_reserved_and_offer_waiting_list()

    def _run_betting_round(self, seated_clients):
        acted_players = set()

        while not self.shutdown_event.is_set():
            active_decision_players = [
                player
                for player in self.game.players
                if not player.folded and not player.all_in
            ]

            if len(self.game.active_players()) <= 1 or not active_decision_players:
                return

            round_complete = True
            for player in active_decision_players:
                if player.current_bet != self.game.current_bet:
                    round_complete = False
                    break

                if player.name not in acted_players:
                    round_complete = False
                    break

            if round_complete:
                return

            player = self.game.players[self.game.action_index]
            if player.folded or player.all_in:
                self.game.action_index = self.game._next_active_index(
                    self.game.action_index
                )
                continue

            legal_actions = self.game.legal_actions(player.name)
            self._send_states_to(seated_clients)
            action_message = self._request_action_with_disconnect_timer(
                player,
                legal_actions,
                seated_clients,
            )

            action = action_message.get("action", "").lower()
            amount = parse_money(
                action_message.get("amount", 0),
                "Amount",
                allow_zero=True,
            )
            try:
                result = self.game.act(player.name, action, amount)
            except ValueError as error:
                current_client = self.table.client_by_name(player.name)
                if current_client is not None and current_client.connected:
                    current_client.send({"type": "error", "message": str(error)})
                continue

            acted_players.add(player.name)
            if action in {"bet", "raise", "all_in"} and self.game.current_bet > 0:
                acted_players = {player.name}

            self._broadcast_to(
                seated_clients,
                {"type": "message", "message": self._describe_action(result)},
            )

    def _request_action_with_disconnect_timer(self, player, legal_actions, seated_clients):
        action_prompt = {
            "type": "request_action",
            "legal_actions": legal_actions,
            "to_call": self.game.current_bet - player.current_bet,
            "min_raise": self.game.min_raise,
            "min_raise_to": self.game.current_bet + self.game.min_raise,
            "max_bet": (
                self.game.max_bet(player.name)
                if hasattr(self.game, "max_bet")
                else None
            ),
            "max_raise_to": (
                self.game.max_raise_total(player.name)
                if hasattr(self.game, "max_raise_total")
                else None
            ),
        }
        prompted_client = None
        countdown_started = False
        remaining = 30

        while not self.shutdown_event.is_set():
            client = self.table.client_by_name(player.name)
            if client is None:
                return {"type": "action", "action": "fold", "amount": 0}

            if client.connected:
                try:
                    if prompted_client is not client:
                        client.send(action_prompt)
                        prompted_client = client

                    readable, _, _ = select.select([client.socket], [], [], 1)
                    if not readable:
                        continue

                    message = client.recv()

                    if message and message.get("type") == "action":
                        if countdown_started:
                            self._broadcast_to(
                                seated_clients,
                                {
                                    "type": "message",
                                    "message": f"{player.name} reconnected and acted.",
                                },
                            )
                        return message

                except (ConnectionError, OSError):
                    client.connected = False

            if not countdown_started:
                countdown_started = True
                self._broadcast_to(
                    seated_clients,
                    {
                        "type": "message",
                        "message": (
                            f"{player.name} disconnected. "
                            "They have 30 seconds to reconnect."
                        ),
                    },
                )

            if remaining <= 0:
                timeout_action = "check" if "check" in legal_actions else "fold"
                self._broadcast_to(
                    seated_clients,
                    {
                        "type": "message",
                        "message": (
                            f"{player.name}'s reconnect timer expired. "
                            f"Auto-{timeout_action}."
                        ),
                    },
                )
                return {"type": "action", "action": timeout_action, "amount": 0}

            self._broadcast_to(
                seated_clients,
                {
                    "type": "disconnect_timer",
                    "player": player.name,
                    "seconds": remaining,
                },
            )
            time.sleep(1)
            remaining -= 1

        return {"type": "action", "action": "fold", "amount": 0}

    def _deal_remaining_board(self, seated_clients):
        if len(self.game.board) < 3:
            self.game.deal_flop()
            self._broadcast_to(
                seated_clients,
                {
                    "type": "message",
                    "message": "Flops dealt." if self.game_class is AllocatorGame else "Flop dealt.",
                },
            )

        if len(self.game.board) < 4:
            self.game.deal_turn()
            self._broadcast_to(
                seated_clients,
                {
                    "type": "message",
                    "message": "Turns dealt." if self.game_class is AllocatorGame else "Turn dealt.",
                },
            )

        if len(self.game.board) < 5:
            self.game.deal_river()
            self._broadcast_to(
                seated_clients,
                {
                    "type": "message",
                    "message": "Rivers dealt." if self.game_class is AllocatorGame else "River dealt.",
                },
            )

        self._send_states_to(seated_clients)

    def _request_allocator_allocations(self, seated_clients):
        self._send_states_to(seated_clients)
        self._broadcast_to(
            seated_clients,
            {
                "type": "message",
                "message": "Allocation phase started. Waiting for all players.",
            },
        )

        errors = []
        threads = []

        for player in list(self.game.active_players()):
            client = self._client_by_name(player.name, seated_clients)
            thread = threading.Thread(
                target=self._collect_allocator_allocation,
                args=(client, player, errors),
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        if errors:
            raise RuntimeError(errors[0])

        self._broadcast_to(
            seated_clients,
            {
                "type": "message",
                "message": "All allocations submitted.",
            },
        )

    def _collect_allocator_allocation(self, client, player, errors):
        while True:
            try:
                client.send(
                    {
                        "type": "request_allocator_allocation",
                        "hand": [str(card) for card in player.hand],
                        "top_board": [str(card) for card in self.game.top_board],
                        "bottom_board": [str(card) for card in self.game.bottom_board],
                    }
                )
                message = client.recv()
                if not message or message.get("type") != "allocator_allocation":
                    errors.append(f"{player.name} disconnected during allocation")
                    return

                top_indexes = self._parse_card_indexes(message.get("top"))
                bottom_indexes = self._parse_card_indexes(message.get("bottom"))
                hand_indexes = self._parse_card_indexes(message.get("hand"))

                self.game.set_allocation(
                    player.name,
                    [player.hand[index - 1] for index in top_indexes],
                    [player.hand[index - 1] for index in bottom_indexes],
                    [player.hand[index - 1] for index in hand_indexes],
                )
                client.send(
                    {
                        "type": "message",
                        "message": "Allocation submitted. Waiting for other players.",
                    }
                )
                return

            except (IndexError, TypeError, ValueError) as error:
                client.send({"type": "error", "message": str(error)})

    @staticmethod
    def _parse_card_indexes(indexes):
        if not isinstance(indexes, list):
            raise ValueError("Allocation indexes must be a list")

        parsed = [int(index) for index in indexes]
        if len(parsed) != 2:
            raise ValueError("Each allocation bucket must contain exactly two cards")

        if len(set(parsed)) != 2:
            raise ValueError("Do not use the same card twice in one bucket")

        if any(index < 1 or index > 6 for index in parsed):
            raise ValueError("Card indexes must be from 1 to 6")

        return parsed

    def _allocator_showdown_details(self):
        active_players = [player for player in self.game.players if not player.folded]
        scores = self.game.calculate_scores()

        return {
            "top": self._allocator_board_detail(
                active_players,
                "top",
                self.game.top_board,
            ),
            "bottom": self._allocator_board_detail(
                active_players,
                "bottom",
                self.game.bottom_board,
            ),
            "hand_strength": self._allocator_hand_strength_detail(active_players),
            "totals": {
                player.name: self._format_points(scores[player.name].total)
                for player in active_players
            },
        }

    def _allocator_board_detail(self, active_players, allocation_name, board):
        player_results = {}
        for player in active_players:
            allocation = self.game.allocations[player.name]
            allocated_cards = getattr(allocation, allocation_name)
            score = HandEvaluator.best_hand(allocated_cards + board)
            player_results[player.name] = {
                "cards": [str(card) for card in allocated_cards],
                "hand_name": score[3],
                "score": score[:2],
            }

        best_score = max(result["score"] for result in player_results.values())
        winners = [
            player_name
            for player_name, result in player_results.items()
            if result["score"] == best_score
        ]
        points = Fraction(1, len(winners))

        return {
            "board": [str(card) for card in board],
            "players": {
                player_name: {
                    "cards": result["cards"],
                    "hand_name": result["hand_name"],
                }
                for player_name, result in player_results.items()
            },
            "winners": [
                {
                    "player": winner,
                    "hand_name": player_results[winner]["hand_name"],
                    "points": self._format_points(points),
                }
                for winner in winners
            ],
        }

    def _allocator_hand_strength_detail(self, active_players):
        player_results = {}
        for player in active_players:
            cards = self.game.allocations[player.name].hand
            rank = self.game.hand_strength_rank(cards)
            label = "pair" if cards[0].rank == cards[1].rank else "high card"
            player_results[player.name] = {
                "cards": [str(card) for card in cards],
                "label": label,
                "rank": rank,
            }

        best_rank = max(result["rank"] for result in player_results.values())
        winners = [
            player_name
            for player_name, result in player_results.items()
            if result["rank"] == best_rank
        ]
        points = Fraction(1, len(winners))

        return {
            "players": {
                player_name: {
                    "cards": result["cards"],
                    "label": result["label"],
                }
                for player_name, result in player_results.items()
            },
            "winners": [
                {
                    "player": winner,
                    "label": player_results[winner]["label"],
                    "points": self._format_points(points),
                }
                for winner in winners
            ],
        }

    @staticmethod
    def _format_points(points):
        if points.denominator == 1:
            return str(points.numerator)

        return f"{points.numerator}/{points.denominator}"

    def _should_skip_to_showdown(self):
        players_with_stack = [
            player
            for player in self.game.active_players()
            if not player.all_in and player.stack > 0
        ]
        return len(self.game.active_players()) > 1 and len(players_with_stack) <= 1

    def _send_states_to(self, clients):
        for client in clients:
            current_client = self.table.client_by_name(client.name)
            if current_client is None or not current_client.connected:
                continue

            try:
                current_client.send(
                    {
                        "type": "state",
                        "state": visible_state_for(self.game, current_client.name),
                        "table": self._table_status(),
                    }
                )
            except ConnectionError:
                current_client.connected = False

    def _ask_next_hand(self, clients):
        responses = []
        responses_lock = threading.Lock()
        threads = []

        for client in clients:
            if self.shutdown_event.is_set():
                return

            if client not in self.table.seated_clients():
                continue

            thread = threading.Thread(
                target=self._collect_next_hand_response,
                args=(client, responses, responses_lock),
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        if self.shutdown_event.is_set():
            return

        for client, wants_next_hand in responses:
            if wants_next_hand:
                continue

            self.table.remove_client(client)
            try:
                client.send(
                    {
                        "type": "session_over",
                        "message": "You left the table.",
                    }
                )
            except ConnectionError:
                pass

    def _collect_next_hand_response(self, client, responses, responses_lock):
        wants_next_hand = False
        try:
            client.send({"type": "request_continue"})
            message = client.recv()
            wants_next_hand = bool(message and message.get("continue") is True)
        except Exception:
            wants_next_hand = False

        if self.shutdown_event.is_set():
            return

        with responses_lock:
            responses.append((client, wants_next_hand))

    def _broadcast_to(self, clients, message):
        for client in clients:
            current_client = self.table.client_by_name(client.name)
            if current_client is None or not current_client.connected:
                continue

            try:
                current_client.send(message)
            except ConnectionError:
                current_client.connected = False

    def _client_by_name(self, name, clients):
        current_client = self.table.client_by_name(name)
        if current_client is not None:
            return current_client

        raise RuntimeError(f"No seated client named {name}")

    @staticmethod
    def _describe_action(result):
        if result.action == "check":
            return f"{result.player} checks."

        if result.action == "fold":
            return f"{result.player} folds."

        if result.action == "call":
            return f"{result.player} calls {result.amount}."

        if result.action == "bet":
            return f"{result.player} bets {result.amount}."

        if result.action == "raise":
            return f"{result.player} raises {result.amount} to {result.current_bet}."

        if result.action == "all_in":
            return f"{result.player} goes all-in for {result.amount}."

        return f"{result.player} {result.action}s."


class NetworkPokerServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.tables = {}
        self.tables_lock = threading.Lock()
        self.clients = set()
        self.clients_lock = threading.Lock()
        self.shutdown_event = threading.Event()

    def run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((self.host, self.port))
                server_socket.listen()
                server_socket.settimeout(1)

                print(f"PokerMeow lobby listening on {self.host}:{self.port}")
                print("Players can create or join tables from the client.")
                self._print_connection_help()
                print("Press Ctrl+C to shut down.")

                while not self.shutdown_event.is_set():
                    try:
                        socket_obj, address = server_socket.accept()
                    except socket.timeout:
                        continue

                    client = Client(socket_obj, address, self.shutdown_event)
                    self._register_client(client)
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client, address),
                        daemon=True,
                    )
                    thread.start()
        except KeyboardInterrupt:
            print("\nShutting down PokerMeow server...")
        finally:
            self.stop()

    def _print_connection_help(self):
        addresses = local_ipv4_addresses()
        if not addresses:
            print("Could not detect a LAN IP. Run 'ipconfig' and look for IPv4 Address.")
            return

        print("Friends on the same Wi-Fi/LAN can connect with:")
        for address in addresses:
            print(f"  python client.py {address} --port {self.port}")

    def stop(self):
        self.shutdown_event.set()
        with self.clients_lock:
            clients = list(self.clients)

        for client in clients:
            client.force_close()

        with self.tables_lock:
            tables = list(self.tables.values())

        for table in tables:
            table.stop()

    def _register_client(self, client):
        with self.clients_lock:
            self.clients.add(client)

    def _unregister_client(self, client):
        with self.clients_lock:
            self.clients.discard(client)

    def _handle_client(self, client, address):
        try:
            self._welcome_client(client)
            action = self._request_lobby_action(client)
            if action == "create":
                table = self._create_table(client)
                table.add_client_to_table(client, address)
            else:
                table = self._request_table_to_join(client)
                table.add_client_to_table(client, address)
        except Exception as error:
            try:
                client.send({"type": "error", "message": str(error)})
            except Exception:
                pass
            client.close()
        finally:
            self._unregister_client(client)

    def _welcome_client(self, client):
        client.send({"type": "welcome", "message": "Connected to PokerMeow lobby."})

    def _request_lobby_action(self, client):
        while True:
            client.send({"type": "request_lobby_action"})
            message = client.recv()
            if not message or message.get("type") != "lobby_action":
                raise RuntimeError("Client disconnected in lobby")

            action = message.get("action")
            if action in {"create", "join"}:
                return action

            client.send({"type": "error", "message": "Choose create or join."})

    def _create_table(self, client):
        client.send({"type": "request_table_config"})
        message = client.recv()
        if not message or message.get("type") != "table_config":
            raise RuntimeError("Client disconnected before table creation")

        game_choice = message.get("game")
        if game_choice == "plo":
            game_class = PotLimitOmahaGame
            game_name = "Pot-Limit Omaha"
        elif game_choice == "allocator":
            game_class = AllocatorGame
            game_name = "Allocator"
        else:
            game_class = NoLimitHoldemGame
            game_name = "No-Limit Texas Hold'em"

        max_seats = self._parse_int(message.get("max_seats"), "Number of seats")
        seat_cap = 10 if game_class is NoLimitHoldemGame else 7
        if max_seats < 2 or max_seats > seat_cap:
            raise RuntimeError(f"Number of seats must be between 2 and {seat_cap}")

        bomb_pot_ante = 0
        if game_class is AllocatorGame:
            small_blind = Decimal("1")
            big_blind = Decimal("2")
            bomb_pot_ante = self._parse_int(
                message.get("bomb_pot_ante"),
                "Bomb pot ante",
            )
            if bomb_pot_ante <= 0:
                raise RuntimeError("Bomb pot ante must be greater than zero")
        else:
            big_blind = parse_money(message.get("big_blind"), "Big blind")
            small_blind = big_blind / Decimal("2")
            if big_blind <= 0:
                raise RuntimeError("Big blind must be greater than zero")

        table_id = self._new_table_id()
        table = PokerTableSession(
            table_id=table_id,
            game_class=game_class,
            game_name=game_name,
            small_blind=small_blind,
            big_blind=big_blind,
            max_seats=max_seats,
            bomb_pot_ante=bomb_pot_ante,
            shutdown_event=self.shutdown_event,
        )

        with self.tables_lock:
            self.tables[table_id] = table

        thread = threading.Thread(target=table.run, daemon=True)
        thread.start()

        client.send(
            {
                "type": "table_created",
                "table_id": table_id,
                "message": f"Created table {table_id}.",
            }
        )
        return table

    def _request_table_to_join(self, client):
        while True:
            client.send({"type": "request_table_id"})
            message = client.recv()
            if not message or message.get("type") != "table_id":
                raise RuntimeError("Client disconnected before choosing a table")

            table_id = str(message.get("table_id", "")).strip().upper()
            with self.tables_lock:
                table = self.tables.get(table_id)

            if table is not None:
                client.send(
                    {
                        "type": "message",
                        "message": f"Joining table {table_id}.",
                    }
                )
                return table

            client.send(
                {
                    "type": "table_not_found",
                    "message": f"No table found with ID {table_id}.",
                }
            )

    def _new_table_id(self):
        alphabet = string.ascii_uppercase + string.digits
        while True:
            table_id = "".join(random.choice(alphabet) for _ in range(4))
            with self.tables_lock:
                if table_id not in self.tables:
                    return table_id

    @staticmethod
    def _parse_int(value, field_name):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise RuntimeError(f"{field_name} must be a whole number")



def main():
    parser = argparse.ArgumentParser(description="PokerMeow lobby server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = NetworkPokerServer(
        host=args.host,
        port=args.port,
    )
    server.run()


def ask_choice(prompt, choices):
    while True:
        value = input(prompt).strip().lower()
        if value in choices:
            return choices[value]

        if value in choices.values():
            return value

        print("Please choose a valid option.")


def ask_positive_int(prompt, default):
    while True:
        value = input(prompt).strip()
        if not value:
            return default

        try:
            number = int(value)
        except ValueError:
            print("Please enter a whole number.")
            continue

        if number <= 0:
            print("Please enter a number greater than zero.")
            continue

        return number


def ask_seat_count(value=None):
    while True:
        if value is None:
            value = ask_positive_int("Number of seats: ", default=10)

        if 2 <= value <= 10:
            return value

        print("Number of seats must be between 2 and 10.")
        value = None


if __name__ == "__main__":
    main()
