import argparse
from collections import deque
import select
import socket
import random
import string
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from allocator import AllocatorGame
from helicopter import HelicopterGame
from config import HOST, MAX_CONNECTIONS, PORT, TIMEOUTS
from game_categories import BoardCategory
from network_protocol import ProtocolError, recv_json, send_json, visible_state_for
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


def run_count_for_votes(player_names, votes):
    player_names = set(player_names)
    if (
        player_names
        and set(votes) == player_names
        and all(votes[name] == "twice" for name in player_names)
    ):
        return 2
    return 1


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
        self.leave_after_hand = False
        self.shutdown_event = shutdown_event or threading.Event()
        self.send_lock = threading.Lock()

    def send(self, message):
        if not self.connected:
            raise ConnectionError("Client is disconnected")

        try:
            with self.send_lock:
                send_json(self.file, message)
        except OSError as error:
            self.connected = False
            raise ConnectionError("Client is disconnected") from error

    def recv(self, stop_event=None):
        if not self.connected:
            return None

        while not self.shutdown_event.is_set():
            if stop_event is not None and stop_event.is_set():
                return None
            try:
                readable, _, _ = select.select(
                    [self.socket],
                    [],
                    [],
                    TIMEOUTS["socket_select"],
                )
            except (OSError, ValueError):
                self.connected = False
                return None

            if not readable:
                continue

            try:
                message = recv_json(self.file)
            except socket.timeout:
                continue
            except ProtocolError:
                self.connected = False
                return None
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
                if (
                    seat is not None
                    and seat.reserved
                    and seat.stack > 0
                ):
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
                    new_client.leave_after_hand = old_client.leave_after_hand
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
            for seat in self.seats:
                if seat is None:
                    continue

                if seat.client.name not in stacks:
                    continue
                seat.stack = stacks[seat.client.name]
                if seat.stack <= 0:
                    seat.reserved = True
                    busted.append(seat.client)
        return busted

    def set_stack(self, client, amount):
        with self.lock:
            for seat in self.seats:
                if seat is not None and seat.client is client:
                    seat.stack = amount
                    return True
        return False

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
        self.current_hand_history = []
        self.chat_messages = deque(maxlen=30)
        self.chat_lock = threading.Lock()
        self.dealer_index = 0
        self.shutdown_event = shutdown_event or threading.Event()

    def run(self):
        print(f"Table {self.table_id} started.")
        print(f"Game: {self.game_name}")
        if issubclass(self.game_class, AllocatorGame):
            print(f"Bomb pot ante: {self.bomb_pot_ante}")
        else:
            print(f"Blinds: {self.small_blind}/{self.big_blind}")
        print(f"Table has {self.table.max_seats} seats.")

        while not self.shutdown_event.is_set():
            self._activate_reserved_and_offer_waiting_list()
            self._poll_control_messages(
                self.table.seated_clients(),
                timeout=0,
            )

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
            self._send_chat_history(client)
            self._send_reconnect_snapshot(client)
            return

        client.name = self._claim_unique_name(client, client.name)
        client.send({"type": "joined", "name": client.name})

        try:
            self._request_buy_in(client)

            with self.all_clients_lock:
                self.all_clients.append(client)

            self._send_chat_history(client)
            self._place_new_client(client, address)
        finally:
            self._release_pending_name(client.name)

    def _table_status(self):
        status = self.table.table_status()
        status["table_id"] = self.table_id
        status["game"] = self.game_name
        return status

    def _broadcast_table_status(self):
        message = {"type": "table", "table": self._table_status()}
        with self.all_clients_lock:
            clients = list(self.all_clients)
        for connected_client in clients:
            if not connected_client.connected:
                continue
            try:
                connected_client.send(message)
            except ConnectionError:
                connected_client.connected = False

    def _send_reconnect_snapshot(self, client):
        table_status = self._table_status()
        try:
            if self.game is None or not self.table.hand_in_progress:
                client.send({"type": "table", "table": table_status})
                return

            game_player = next(
                (
                    player
                    for player in self.game.players
                    if player.name.lower() == client.name.lower()
                ),
                None,
            )
            if game_player is None:
                client.send({"type": "table", "table": table_status})
                return

            client.send(
                {
                    "type": "state",
                    "state": visible_state_for(self.game, client.name),
                    "table": table_status,
                }
            )
            client.send(
                {
                    "type": "hand_history",
                    "history": list(self.current_hand_history),
                }
            )
        except ConnectionError:
            client.connected = False

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
            self._broadcast_table_status()
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

        self._broadcast_table_status()

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
        self.current_hand_history = []
        seated_clients = self.table.seated_clients()
        player_stacks = self.table.seated_player_stacks()

        if issubclass(self.game_class, AllocatorGame):
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
            runout_boards = None
            self.game.start_hand()
            self._broadcast_hand_message(seated_clients, "New hand started.")
            self._send_states_to(seated_clients)

            if not issubclass(self.game_class, AllocatorGame):
                self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and self._should_skip_to_showdown():
                runout_boards = self._deal_all_in_runout(seated_clients)
            elif len(self.game.active_players()) > 1:
                self.game.deal_flop()
                self._broadcast_hand_message(
                    seated_clients,
                    "Flops dealt." if issubclass(self.game_class, AllocatorGame) else "Flop dealt.",
                )
                self._send_states_to(seated_clients)
                self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and len(self.game.board) == 3:
                if self._should_skip_to_showdown():
                    runout_boards = self._deal_all_in_runout(seated_clients)
                else:
                    self.game.deal_turn()
                    self._broadcast_hand_message(
                        seated_clients,
                        "Turns dealt." if issubclass(self.game_class, AllocatorGame) else "Turn dealt.",
                    )
                    self._send_states_to(seated_clients)
                    self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and len(self.game.board) == 4:
                if self._should_skip_to_showdown():
                    runout_boards = self._deal_all_in_runout(seated_clients)
                else:
                    self.game.deal_river()
                    self._broadcast_hand_message(
                        seated_clients,
                        "Rivers dealt." if issubclass(self.game_class, AllocatorGame) else "River dealt.",
                    )
                    self._send_states_to(seated_clients)
                    self._run_betting_round(seated_clients)

            if len(self.game.active_players()) > 1 and len(self.game.board) < 5:
                self._deal_remaining_board(seated_clients)

            if issubclass(self.game_class, AllocatorGame) and len(self.game.active_players()) > 1:
                self._request_allocator_allocations(seated_clients)

            if runout_boards and len(runout_boards) == 2:
                result = self.game.showdown_boards(runout_boards)
            else:
                result = self.game.showdown()
            showdown_scores = None
            if result.hand_name == "uncontested":
                player_hand_names = {}
                winner_hand_names = {
                    winner: result.hand_name
                    for winner in result.winners
                }
                allocator_details = None
            elif issubclass(self.game_class, AllocatorGame):
                scores = self.game.calculate_scores()
                player_hand_names = {
                    player.name: f"{scores[player.name].total} points"
                    for player in self.game.players
                    if not player.folded
                }
                winner_hand_names = {
                    winner: player_hand_names[winner]
                    for winner in result.winners
                }
                allocator_details = self._allocator_showdown_details()
            elif runout_boards and len(runout_boards) == 2:
                board_scores = [
                    {
                        player.name: self.game._score_hand(player.hand, board)
                        for player in self.game.players
                        if not player.folded
                    }
                    for board in runout_boards
                ]
                player_hand_names = {
                    player.name: " / ".join(
                        scores[player.name][3]
                        for scores in board_scores
                    )
                    for player in self.game.players
                    if not player.folded
                }
                winner_hand_names = {
                    winner: player_hand_names[winner]
                    for winner in result.winners
                }
                allocator_details = None
            elif self.game_class is PotLimitOmahaGame and len(self.game.board) == 5:
                showdown_scores = {
                    player.name: self.game._best_plo_hand(
                        player.hand,
                        self.game.board,
                    )
                    for player in self.game.players
                    if not player.folded
                }
                player_hand_names = {
                    name: score[3] for name, score in showdown_scores.items()
                }
                winner_hand_names = {
                    winner: player_hand_names[winner]
                    for winner in result.winners
                }
                allocator_details = None
            elif len(self.game.board) == 5:
                showdown_scores = {
                    # Board-first ordering makes a true board-playing chop
                    # spotlight the shared five cards instead of an equivalent
                    # private card with the same rank.
                    player.name: HandEvaluator.best_hand(self.game.board + player.hand)
                    for player in self.game.players
                    if not player.folded
                }
                player_hand_names = {
                    name: score[3] for name, score in showdown_scores.items()
                }
                winner_hand_names = {
                    winner: player_hand_names[winner]
                    for winner in result.winners
                }
                allocator_details = None
            else:
                player_hand_names = {
                    player.name: result.hand_name
                    for player in self.game.players
                    if not player.folded
                }
                winner_hand_names = {
                    winner: player_hand_names[winner]
                    for winner in result.winners
                }
                allocator_details = None

            revealed_hands = []
            if result.hand_name != "uncontested":
                for player in self.game.players:
                    if player.folded:
                        continue
                    hand_info = {
                        "player": player.name,
                        "hand": [str(card) for card in player.hand],
                        "hand_name": player_hand_names[player.name],
                    }
                    if allocator_details is not None:
                        hand_info["rankings"] = {
                            "top": allocator_details["top"]["players"][
                                player.name
                            ]["hand_name"],
                            "bottom": allocator_details["bottom"]["players"][
                                player.name
                            ]["hand_name"],
                            "hand_strength": allocator_details[
                                "hand_strength"
                            ]["players"][player.name]["label"],
                            "total": allocator_details["totals"][player.name],
                        }
                    revealed_hands.append(hand_info)

            amount_won = self._net_winnings(result.amount_won)
            self._record_showdown_history(
                result,
                winner_hand_names,
                amount_won,
                revealed_hands,
            )
            self._send_states_to(seated_clients)
            showdown_delay = self._showdown_display_seconds(result)
            spotlight_cards = None
            if (
                result.hand_name != "uncontested"
                and self.game_class in {NoLimitHoldemGame, PotLimitOmahaGame}
                and showdown_scores
            ):
                spotlight_cards = self._spotlight_cards_for_scores(showdown_scores)
            self._broadcast_to(
                seated_clients,
                {
                    "type": "showdown",
                    "winners": result.winners,
                    "hand_name": result.hand_name,
                    "winner_hand_names": winner_hand_names,
                    "player_hand_names": player_hand_names,
                    "board": [str(card) for card in self.game.board],
                    "runout_boards": (
                        [
                            [str(card) for card in board]
                            for board in runout_boards
                        ]
                        if runout_boards and len(runout_boards) == 2
                        else None
                    ),
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
                    "amount_won": amount_won,
                    "payouts": dict(result.amount_won),
                    "hands": revealed_hands,
                    "display_seconds": showdown_delay,
                    "spotlight_cards": spotlight_cards,
                },
            )

            self._wait_for_showdown_display(seated_clients, showdown_delay)
            busted_clients = self.table.update_stacks(self.game)
            leaving_clients = self._remove_scheduled_leavers()
            busted_clients = [
                client
                for client in busted_clients
                if client not in leaving_clients
            ]
            self._offer_rebuys(busted_clients)
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
            previous_current_bet = self.game.current_bet
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

            self._broadcast_hand_message(
                seated_clients,
                self._describe_action(
                    result,
                    previous_current_bet,
                ),
            )

    def _request_action_with_disconnect_timer(self, player, legal_actions, seated_clients):
        action_prompt = {
            "type": "request_action",
            "legal_actions": legal_actions,
            "to_call": self.game.amount_to_call(player.name),
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
        remaining = TIMEOUTS["disconnect_timer"]

        while not self.shutdown_event.is_set():
            client = self.table.client_by_name(player.name)
            if client is None:
                return {"type": "action", "action": "fold", "amount": 0}

            if client.connected:
                try:
                    self._poll_control_messages(
                        [
                            seated_client
                            for seated_client in seated_clients
                            if seated_client.name != player.name
                        ],
                        timeout=0,
                    )
                    if prompted_client is not client:
                        client.send(action_prompt)
                        prompted_client = client

                    readable, _, _ = select.select(
                        [client.socket],
                        [],
                        [],
                        TIMEOUTS["socket_select"],
                    )
                    if not readable:
                        continue

                    message = client.recv()

                    if message and message.get("type") == "leave_table":
                        self._handle_leave_request(client)
                        continue
                    if message and message.get("type") == "cancel_leave":
                        self._handle_cancel_leave_request(client)
                        continue
                    if message and message.get("type") == "chat":
                        self._handle_chat_message(client, message)
                        continue

                    if message and message.get("type") == "action":
                        if countdown_started:
                            self._broadcast_hand_message(
                                seated_clients,
                                f"{player.name} reconnected and acted.",
                            )
                        return message

                except (ConnectionError, OSError):
                    client.connected = False

            if not countdown_started:
                countdown_started = True
                self._broadcast_hand_message(
                    seated_clients,
                    (
                        f"{player.name} disconnected. "
                        f"They have {TIMEOUTS['disconnect_timer']} seconds to reconnect."
                    ),
                )

            if remaining <= 0:
                timeout_action = "check" if "check" in legal_actions else "fold"
                self._broadcast_hand_message(
                    seated_clients,
                    (
                        f"{player.name}'s reconnect timer expired. "
                        f"Auto-{timeout_action}."
                    ),
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
            self._broadcast_hand_message(
                seated_clients,
                "Flops dealt." if issubclass(self.game_class, AllocatorGame) else "Flop dealt.",
            )

        if len(self.game.board) < 4:
            self.game.deal_turn()
            self._broadcast_hand_message(
                seated_clients,
                "Turns dealt." if issubclass(self.game_class, AllocatorGame) else "Turn dealt.",
            )

        if len(self.game.board) < 5:
            self.game.deal_river()
            self._broadcast_hand_message(
                seated_clients,
                "Rivers dealt." if issubclass(self.game_class, AllocatorGame) else "River dealt.",
            )

        self._send_states_to(seated_clients)

    def _request_allocator_allocations(self, seated_clients):
        self._send_states_to(seated_clients)

    def _deal_all_in_runout(self, seated_clients):
        run_count = self._request_run_it_vote(seated_clients)
        starting_board = list(self.game.board)
        boards = []

        for run_number in range(run_count):
            self.game.board = list(starting_board)
            self._deal_remaining_board(seated_clients)
            boards.append(list(self.game.board))
            if run_count == 2:
                self._broadcast_hand_message(
                    seated_clients,
                    f"Run {run_number + 1}: "
                    + " ".join(str(card) for card in self.game.board),
                )

        self.game.board = list(boards[0])
        self._send_states_to(seated_clients)
        return boards

    def _request_run_it_vote(self, seated_clients):
        if (
            self.game.board_category is not BoardCategory.SINGLE_BOARD
            or len(self.game.board) >= 5
        ):
            return 1

        active_names = {
            player.name
            for player in self.game.active_players()
        }
        clients = [
            self.table.client_by_name(name)
            for name in active_names
        ]
        connected_clients = [
            client
            for client in clients
            if client is not None and client.connected
        ]
        votes = {}
        deadline = time.monotonic() + TIMEOUTS["run_it_vote"]
        prompt = {
            "type": "request_run_it",
            "seconds": TIMEOUTS["run_it_vote"],
        }
        self._broadcast_hand_message(
            seated_clients,
            "All-in. Players have 5 seconds to choose run it once or twice.",
        )
        self._broadcast_to(connected_clients, prompt)

        while not self.shutdown_event.is_set() and time.monotonic() < deadline:
            if len(votes) == len(active_names):
                break
            readable_clients = [
                client
                for client in connected_clients
                if client.name not in votes and client.connected
            ]
            if not readable_clients:
                break
            timeout = min(0.1, max(0, deadline - time.monotonic()))
            readable, _, _ = select.select(
                [client.socket for client in readable_clients],
                [],
                [],
                timeout,
            )
            for socket_obj in readable:
                client = next(
                    item for item in readable_clients
                    if item.socket is socket_obj
                )
                try:
                    message = client.recv()
                except (ConnectionError, OSError):
                    client.connected = False
                    continue
                if not message:
                    client.connected = False
                    continue
                if message.get("type") == "leave_table":
                    self._handle_leave_request(client)
                    votes[client.name] = "once"
                    continue
                if message.get("type") == "cancel_leave":
                    self._handle_cancel_leave_request(client)
                    continue
                if message.get("type") == "chat":
                    self._handle_chat_message(client, message)
                    continue
                if message.get("type") != "run_it_vote":
                    continue
                choice = str(message.get("choice", "")).lower()
                if choice not in {"once", "twice"}:
                    continue
                votes[client.name] = choice
                if choice == "once":
                    self._broadcast_hand_message(
                        seated_clients,
                        f"{client.name} chose once. Running it once.",
                    )
                    return 1

        if run_count_for_votes(active_names, votes) == 2:
            self._broadcast_hand_message(
                seated_clients,
                "Everyone chose twice. Running it twice.",
            )
            return 2

        self._broadcast_hand_message(
            seated_clients,
            "Run-it vote expired without unanimous twice. Running it once.",
        )
        return 1
        self._broadcast_hand_message(
            seated_clients,
            "Allocation phase started. Waiting for all players.",
        )

        errors = []
        threads = []
        ready_players = set()
        ready_condition = threading.Condition()
        allocations_locked = threading.Event()
        active_players = list(self.game.active_players())

        for player in active_players:
            client = self._client_by_name(player.name, seated_clients)
            thread = threading.Thread(
                target=self._collect_allocator_allocation,
                args=(
                    client, player, errors, ready_players, ready_condition,
                    allocations_locked,
                ),
            )
            thread.start()
            threads.append(thread)

        # Require the whole table to remain ready briefly. This lets an
        # already-sent Cancel ready reach the server before allocations lock.
        with ready_condition:
            while not errors:
                while len(ready_players) < len(active_players) and not errors:
                    ready_condition.wait()
                if errors:
                    break
                changed = ready_condition.wait(timeout=0.5)
                if not changed and len(ready_players) == len(active_players):
                    allocations_locked.set()
                    break
            if errors:
                allocations_locked.set()

        for thread in threads:
            thread.join()

        if errors:
            raise RuntimeError(errors[0])

        for player in active_players:
            client = self._client_by_name(player.name, seated_clients)
            client.send({"type": "allocator_locked"})

        self._broadcast_hand_message(
            seated_clients,
            "All allocations submitted.",
        )

    def _collect_allocator_allocation(
        self, client, player, errors, ready_players, ready_condition,
        allocations_locked,
    ):
        requested = False
        while True:
            try:
                if not requested:
                    client.send(
                        {
                            "type": "request_allocator_allocation",
                            "hand": [str(card) for card in player.hand],
                            "top_board": [str(card) for card in self.game.top_board],
                            "bottom_board": [str(card) for card in self.game.bottom_board],
                        }
                    )
                    requested = True
                message = client.recv(stop_event=allocations_locked)
                if allocations_locked.is_set() and message is None:
                    return
                if message and message.get("type") == "leave_table":
                    self._handle_leave_request(client)
                    continue
                if message and message.get("type") == "cancel_leave":
                    self._handle_cancel_leave_request(client)
                    continue
                if message and message.get("type") == "chat":
                    self._handle_chat_message(client, message)
                    continue
                if not message:
                    with ready_condition:
                        errors.append(f"{player.name} disconnected during allocation")
                        ready_condition.notify_all()
                    return

                if message.get("type") == "allocator_ready":
                    if message.get("ready") is not False:
                        client.send({"type": "error", "message": "Invalid ready state"})
                        continue
                    with ready_condition:
                        ready_players.discard(player.name)
                        ready_condition.notify_all()
                    client.send(
                        {"type": "message", "message": "Ready cancelled."}
                    )
                    continue

                if message.get("type") != "allocator_allocation":
                    with ready_condition:
                        errors.append(f"{player.name} sent an invalid allocation response")
                        ready_condition.notify_all()
                    return

                top_indexes = self._parse_card_indexes(message.get("top"), len(player.hand))
                bottom_indexes = self._parse_card_indexes(message.get("bottom"), len(player.hand))
                hand_indexes = self._parse_card_indexes(message.get("hand"), len(player.hand))

                self.game.set_allocation(
                    player.name,
                    [player.hand[index - 1] for index in top_indexes],
                    [player.hand[index - 1] for index in bottom_indexes],
                    [player.hand[index - 1] for index in hand_indexes],
                )
                with ready_condition:
                    ready_players.add(player.name)
                    ready_condition.notify_all()
                client.send(
                    {
                        "type": "message",
                        "message": "Ready. Waiting for all players.",
                    }
                )

            except (IndexError, TypeError, ValueError) as error:
                client.send({"type": "error", "message": str(error)})

    @staticmethod
    def _parse_card_indexes(indexes, max_index=6):
        if not isinstance(indexes, list):
            raise ValueError("Allocation indexes must be a list")

        parsed = [int(index) for index in indexes]
        if len(parsed) != 2:
            raise ValueError("Each allocation bucket must contain exactly two cards")

        if len(set(parsed)) != 2:
            raise ValueError("Do not use the same card twice in one bucket")

        if any(index < 1 or index > max_index for index in parsed):
            raise ValueError(f"Card indexes must be from 1 to {max_index}")

        return parsed

    def _allocator_showdown_details(self):
        active_players = [player for player in self.game.players if not player.folded]
        scores = self.game.calculate_scores()
        side_pots = []

        for pot_result in getattr(self.game, "pot_results", [])[1:]:
            eligible_names = set(pot_result["eligible_players"])
            eligible_players = [
                player
                for player in active_players
                if player.name in eligible_names
            ]
            pot_scores = pot_result["scores"]
            side_pots.append(
                {
                    "name": pot_result["name"],
                    "amount": pot_result["amount"],
                    "top": self._allocator_board_detail(
                        eligible_players,
                        "top",
                        self.game.top_board,
                    ),
                    "bottom": self._allocator_board_detail(
                        eligible_players,
                        "bottom",
                        self.game.bottom_board,
                    ),
                    "hand_strength": self._allocator_hand_strength_detail(
                        eligible_players
                    ),
                    "totals": {
                        player.name: self._format_points(pot_scores[player.name].total)
                        for player in eligible_players
                    },
                    "winners": pot_result["winners"],
                }
            )

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
            "side_pots": side_pots,
        }

    def _allocator_board_detail(self, active_players, allocation_name, board):
        details = self.game.board_score_details(
            active_players,
            allocation_name,
            board,
        )
        player_results = details["players"]

        return {
            "board": [str(card) for card in details["board"]],
            "players": {
                player_name: {
                    "cards": [str(card) for card in result["cards"]],
                    "hand_name": result["hand_name"],
                    "best_five": [str(card) for card in result["best_five"]],
                }
                for player_name, result in player_results.items()
            },
            "winners": [
                {
                    "player": winner,
                    "hand_name": player_results[winner]["hand_name"],
                    "points": self._format_points(details["points"]),
                }
                for winner in details["winners"]
            ],
        }

    def _allocator_hand_strength_detail(self, active_players):
        details = self.game.hand_strength_score_details(active_players)
        player_results = details["players"]

        return {
            "players": {
                player_name: {
                    "cards": [str(card) for card in result["cards"]],
                    "label": result["label"],
                }
                for player_name, result in player_results.items()
            },
            "winners": [
                {
                    "player": winner,
                    "label": player_results[winner]["label"],
                    "points": self._format_points(details["points"]),
                }
                for winner in details["winners"]
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

    def _broadcast_to(self, clients, message):
        for client in clients:
            current_client = self.table.client_by_name(client.name)
            if current_client is None or not current_client.connected:
                continue

            try:
                current_client.send(message)
            except ConnectionError:
                current_client.connected = False

    def _broadcast_hand_message(self, clients, text):
        if not text:
            return
        self.current_hand_history.append(str(text))
        self._broadcast_to(
            clients,
            {
                "type": "message",
                "message": str(text),
            },
        )

    def _record_showdown_history(
        self,
        result,
        winner_hand_names,
        amount_won,
        revealed_hands,
    ):
        self.current_hand_history.append("Showdown.")
        winners = ", ".join(
            f"{winner} ({winner_hand_names.get(winner, result.hand_name)})"
            for winner in result.winners
        )
        self.current_hand_history.append(f"Winners: {winners}.")
        for name, amount in amount_won.items():
            self.current_hand_history.append(f"{name} wins {amount}.")
        for hand_info in revealed_hands:
            cards = ", ".join(hand_info.get("hand", []))
            self.current_hand_history.append(
                f"{hand_info['player']} shows {cards} "
                f"({hand_info.get('hand_name', 'unknown hand')})."
            )

    def _net_winnings(self, gross_winnings):
        contributions = {
            player.name: player.total_committed
            for player in self.game.players
        }
        return {
            name: amount - contributions.get(name, 0)
            for name, amount in gross_winnings.items()
        }

    def _poll_control_messages(self, clients, timeout=0):
        connected_clients = []
        for client in clients:
            current = self.table.client_by_name(client.name)
            if current is not None and current.connected:
                connected_clients.append(current)
        if not connected_clients:
            if timeout:
                self.shutdown_event.wait(timeout)
            return

        sockets = [client.socket for client in connected_clients]
        try:
            readable, _, _ = select.select(sockets, [], [], timeout)
        except (OSError, ValueError):
            return
        clients_by_socket = {
            client.socket: client
            for client in connected_clients
        }
        for socket_obj in readable:
            client = clients_by_socket[socket_obj]
            try:
                message = client.recv()
            except (ConnectionError, OSError):
                client.connected = False
                continue
            if message and message.get("type") == "leave_table":
                self._handle_leave_request(client)
            elif message and message.get("type") == "cancel_leave":
                self._handle_cancel_leave_request(client)
            elif message and message.get("type") == "chat":
                self._handle_chat_message(client, message)

    def _handle_chat_message(self, client, message):
        text = str(message.get("message", "")).strip()
        if not text:
            return
        chat_message = {
            "player": client.name,
            "message": text[:500],
        }
        with self.chat_lock:
            self.chat_messages.append(chat_message)
        self._broadcast_all({"type": "chat", **chat_message})

    def _send_chat_history(self, client):
        with self.chat_lock:
            messages = [dict(message) for message in self.chat_messages]
        try:
            client.send(
                {
                    "type": "chat_history",
                    "messages": messages,
                }
            )
        except ConnectionError:
            client.connected = False

    def _broadcast_all(self, message):
        with self.all_clients_lock:
            clients = list(self.all_clients)
        for client in clients:
            if not client.connected:
                continue
            try:
                client.send(message)
            except ConnectionError:
                client.connected = False

    def _handle_leave_request(self, client):
        player = None
        if self.game is not None:
            player = next(
                (
                    game_player
                    for game_player in self.game.players
                    if game_player.name == client.name
                ),
                None,
            )
        if (
            self.table.hand_in_progress
            and player is not None
            and not player.folded
        ):
            client.leave_after_hand = True
            try:
                client.send(
                    {
                        "type": "leave_scheduled",
                        "message": (
                            "You are still in this hand and will leave "
                            "automatically after it ends."
                        ),
                    }
                )
            except ConnectionError:
                client.connected = False
            return
        self._remove_client_from_table(client)

    def _handle_cancel_leave_request(self, client):
        if not client.leave_after_hand:
            try:
                client.send(
                    {
                        "type": "leave_cancelled",
                        "message": "No pending leave request.",
                    }
                )
            except ConnectionError:
                client.connected = False
            return

        client.leave_after_hand = False
        try:
            client.send(
                {
                    "type": "leave_cancelled",
                    "message": "Leave cancelled. You will stay at the table.",
                }
            )
        except ConnectionError:
            client.connected = False

    def _wait_for_showdown_display(self, clients, duration=None):
        duration = TIMEOUTS["showdown_display"] if duration is None else duration
        deadline = time.monotonic() + duration
        while not self.shutdown_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._poll_control_messages(
                clients,
                timeout=min(remaining, 0.25),
            )

    def _showdown_display_seconds(self, result):
        if result.hand_name == "uncontested":
            return 2
        if issubclass(self.game_class, AllocatorGame):
            return 15
        return TIMEOUTS["showdown_display"]

    @staticmethod
    def _spotlight_cards_for_scores(scores):
        if not scores:
            return None
        strongest = max(score[:2] for score in scores.values())
        cards = []
        for score in scores.values():
            if score[:2] != strongest:
                continue
            for card in score[2]:
                card_text = str(card)
                if card_text not in cards:
                    cards.append(card_text)
        return cards

    def _remove_scheduled_leavers(self):
        leaving_clients = [
            client
            for client in self.table.seated_clients()
            if client.leave_after_hand
        ]
        for client in leaving_clients:
            self._remove_client_from_table(client)
        return leaving_clients

    def _remove_client_from_table(self, client):
        client.leave_after_hand = False
        self.table.remove_client(client)
        try:
            client.send(
                {
                    "type": "left_table",
                    "message": "You left the table.",
                }
            )
        except ConnectionError:
            client.connected = False

    def _offer_rebuys(self, busted_clients):
        for client in busted_clients:
            thread = threading.Thread(
                target=self._handle_rebuy,
                args=(client,),
                daemon=True,
            )
            thread.start()

    def _handle_rebuy(self, client):
        rebuy_amount = None
        try:
            client.send(
                {
                    "type": "request_rebuy",
                    "message": "You are out of chips. Rebuy to keep your seat.",
                    "default_amount": client.buy_in,
                    "seconds": TIMEOUTS["rebuy"],
                }
            )
            readable, _, _ = select.select(
                [client.socket],
                [],
                [],
                TIMEOUTS["rebuy"],
            )
            if readable:
                response = client.recv()
                if response and response.get("type") == "rebuy":
                    if response.get("rebuy") is True:
                        amount = parse_money(response.get("amount"), "Rebuy")
                        if amount > 0:
                            rebuy_amount = amount
        except (ConnectionError, OSError, TypeError, ValueError):
            rebuy_amount = None

        if rebuy_amount is not None and self.table.set_stack(client, rebuy_amount):
            client.buy_in = rebuy_amount
            try:
                client.send(
                    {
                        "type": "rebought",
                        "amount": rebuy_amount,
                        "message": f"Rebuy successful. Your stack is {rebuy_amount}.",
                    }
                )
            except ConnectionError:
                self.table.remove_client(client)
            return

        self.table.remove_client(client)
        try:
            client.send(
                {
                    "type": "session_over",
                    "message": "You left the table after busting.",
                }
            )
        except ConnectionError:
            pass

    def _client_by_name(self, name, clients):
        current_client = self.table.client_by_name(name)
        if current_client is not None:
            return current_client

        raise RuntimeError(f"No seated client named {name}")

    @staticmethod
    def _describe_action(result, previous_current_bet=0):
        if result.action == "check":
            return f"{result.player} checks."

        if result.action == "fold":
            return f"{result.player} folds."

        if result.action == "call":
            return f"{result.player} calls {result.amount}."

        if result.action == "bet":
            return f"{result.player} bets {result.amount}."

        if result.action == "raise":
            raise_amount = result.current_bet - previous_current_bet
            return (
                f"{result.player} raises {raise_amount} "
                f"to {result.current_bet}."
            )

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
                server_socket.listen(MAX_CONNECTIONS)
                server_socket.settimeout(TIMEOUTS["accept"])

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
        print("Friends over the public Internet should connect to your public IP")
        print(f"after your router forwards TCP port {self.port} to this computer.")

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
        elif game_choice == "helicopter":
            game_class = HelicopterGame
            game_name = "Helicopter"
        else:
            game_class = NoLimitHoldemGame
            game_name = "No-Limit Texas Hold'em"

        max_seats = self._parse_int(message.get("max_seats"), "Number of seats")
        seat_cap = 10 if game_class is NoLimitHoldemGame else (6 if game_class is HelicopterGame else 7)
        if max_seats < 2 or max_seats > seat_cap:
            raise RuntimeError(f"Number of seats must be between 2 and {seat_cap}")

        bomb_pot_ante = 0
        if issubclass(game_class, AllocatorGame):
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
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    server = NetworkPokerServer(
        host=args.host,
        port=args.port,
    )
    server.run()


if __name__ == "__main__":
    main()
