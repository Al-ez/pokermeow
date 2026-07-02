import argparse
from decimal import Decimal, InvalidOperation
import select
import socket
import sys
import time

try:
    import msvcrt
except ImportError:
    msvcrt = None

from config import PORT, TIMEOUTS
from network_protocol import ProtocolError, recv_json, send_json


class ServerDisconnected(Exception):
    pass

_disconnect_checker = None


def set_disconnect_checker(checker):
    global _disconnect_checker
    _disconnect_checker = checker


def prompt_input(prompt):
    if msvcrt is None or _disconnect_checker is None:
        return input(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars = []

    while True:
        if _disconnect_checker():
            print("\nDisconnected from server.")
            raise ServerDisconnected

        if not msvcrt.kbhit():
            time.sleep(0.05)
            continue

        char = msvcrt.getwch()
        if char in {"\r", "\n"}:
            print()
            return "".join(chars)

        if char == "\003":
            raise KeyboardInterrupt

        if char == "\b":
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue

        if char in {"\x00", "\xe0"}:
            msvcrt.getwch()
            continue

        chars.append(char)
        sys.stdout.write(char)
        sys.stdout.flush()


def show_cards(cards):
    return ", ".join(cards) if cards else "(empty)"


def seat_label(seat):
    seat_number = seat["seat"]
    status = seat["status"]
    player = seat["player"]

    if status == "open":
        return f"{seat_number}: open"

    if status == "closed":
        return f"{seat_number}: closed"

    if status == "reserved":
        return f"{seat_number}: {player} (reserved)"

    return f"{seat_number}: {player}"


def fit_label(text, width=22):
    if len(text) <= width:
        return text.ljust(width)

    return text[: width - 3] + "..."


def show_table_drawing(table):
    seats_by_number = {
        seat["seat"]: fit_label(seat_label(seat), 20)
        for seat in table["seats"]
    }
    table_title = "POKERMEOW TABLE"
    if table.get("table_id"):
        table_title = f"POKERMEOW TABLE {table['table_id']}"

    def seat(number):
        return seats_by_number.get(number, fit_label(f"{number}: open", 20))

    def side_seat(number):
        return seat(number).strip()

    print("\n" + " " * 31 + table_title)
    print(" " * 18 + f"{seat(1)}  {seat(2)}  {seat(3)}")
    print(" " * 14 + "." + "-" * 72 + ".")
    print(" " * 12 + " /" + " " * 74 + "\\")
    print(f" {side_seat(10)}   /" + " " * 34 + "TABLE" + " " * 37 + f"\\ {side_seat(4)}")
    print(" " * 11 + "|" + " " * 78 + "|")
    print(f" {side_seat(9)}    \\" + " " * 76 + f"/ {side_seat(5)}")
    print(" " * 12 + " \\" + " " * 74 + "/")
    print(" " * 14 + "'" + "-" * 72 + "'")
    print(" " * 18 + f"{seat(8)}  {seat(7)}  {seat(6)}")

    waiting = table.get("waiting", [])
    if waiting:
        print(f"Waiting list: {', '.join(waiting)}")


def show_state(state, table=None):
    if table is not None:
        show_table_drawing(table)

    print("\n" + "=" * 60)
    print(f"Pot: {state['pot']}")
    if "top_board" in state:
        print(f"Top board: {show_cards(state['top_board'])}")
        print(f"Bottom board: {show_cards(state['bottom_board'])}")
    else:
        print(f"Board: {show_cards(state['board'])}")
    print(f"Current bet: {state['current_bet']}")
    print(f"Dealer: {state['dealer']}")
    print("-" * 60)

    for name, player in state["players"].items():
        status = []
        if player["folded"]:
            status.append("folded")
        if player["all_in"]:
            status.append("all-in")

        status_text = f" ({', '.join(status)})" if status else ""
        if "hand" in player:
            hand_text = show_cards(player["hand"])
        else:
            hand_text = f"[{player['hand_size']} hidden cards]"

        print(
            f"{name}: stack={player['stack']} "
            f"bet={player['current_bet']} "
            f"committed={player['total_committed']} "
            f"hand={hand_text}{status_text}"
        )


def ask_action(legal_actions):
    while True:
        print(f"\nLegal actions: {', '.join(legal_actions)}")
        action = prompt_input("Your action: ").strip().lower()
        if action not in legal_actions:
            print("That action is not legal right now.")
            continue

        amount = 0
        if action in {"bet", "raise"}:
            while True:
                raw_amount = prompt_input("Amount: ").strip()
                try:
                    amount = Decimal(raw_amount)
                    if not amount.is_finite():
                        raise InvalidOperation
                    break
                except InvalidOperation:
                    print("Please enter a valid number.")

        return action, amount


def ask_seat(available_seats):
    while True:
        print(f"\nAvailable seats: {', '.join(str(seat) for seat in available_seats)}")
        raw_seat = prompt_input("Choose your seat: ").strip()
        try:
            seat = int(raw_seat)
        except ValueError:
            print("Please enter a seat number.")
            continue

        if seat not in available_seats:
            print("That seat is not available.")
            continue

        return seat


def ask_buy_in():
    while True:
        raw_amount = prompt_input("Buy-in amount: ").strip()
        try:
            amount = Decimal(raw_amount)
            if not amount.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            print("Please enter a valid number.")
            continue

        if amount <= 0:
            print("Buy-in must be greater than zero.")
            continue

        return amount


def ask_rebuy(default_amount):
    while True:
        raw_amount = prompt_input(
            f"Rebuy amount [{default_amount}] (blank to leave): "
        ).strip()
        if not raw_amount:
            return None
        try:
            amount = Decimal(raw_amount)
            if not amount.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            print("Please enter a valid number.")
            continue
        if amount <= 0:
            print("Rebuy must be greater than zero.")
            continue
        return amount


def ask_blinds():
    options = [
        ("1", "0.1/0.2", Decimal("0.2")),
        ("2", "0.25/0.5", Decimal("0.5")),
        ("3", "0.5/1", Decimal("1")),
        ("4", "1/2", Decimal("2")),
        ("5", "2.5/5", Decimal("5")),
        ("6", "5/10", Decimal("10")),
        ("7", "10/20", Decimal("20")),
    ]

    while True:
        print("\nChoose blinds:")
        for key, label, _ in options:
            print(f"  {key}. {label}")

        choice = prompt_input("Blinds: ").strip()
        for key, _, big_blind in options:
            if choice == key:
                return big_blind

        print("Please choose 1 through 7.")


def ask_lobby_action():
    while True:
        choice = prompt_input("Choose: [1] create table  [2] join table: ").strip().lower()
        if choice in {"1", "create", "c"}:
            return "create"

        if choice in {"2", "join", "j"}:
            return "join"

        print("Please choose create or join.")


def ask_positive_int(prompt, default=None):
    while True:
        raw_value = prompt_input(prompt).strip()
        if not raw_value and default is not None:
            return default

        try:
            value = int(raw_value)
        except ValueError:
            print("Please enter a whole number.")
            continue

        if value <= 0:
            print("Please enter a number greater than zero.")
            continue

        return value


def ask_table_config():
    while True:
        game_choice = prompt_input("Choose game: [1] NLH  [2] PLO  [3] Allocator: ").strip()
        if game_choice == "1":
            game = "nlh"
            break
        if game_choice == "2":
            game = "plo"
            break
        if game_choice == "3":
            game = "allocator"
            break
        print("Please choose 1, 2, or 3.")

    seat_cap = 10 if game == "nlh" else 7
    max_seats = ask_positive_int(
        f"Number of seats [{seat_cap}]: ",
        default=seat_cap,
    )
    while max_seats < 2 or max_seats > seat_cap:
        print(f"Number of seats must be between 2 and {seat_cap}.")
        max_seats = ask_positive_int(
            f"Number of seats [{seat_cap}]: ",
            default=seat_cap,
        )

    config = {
        "type": "table_config",
        "game": game,
        "max_seats": max_seats,
    }

    if game == "allocator":
        config["bomb_pot_ante"] = ask_positive_int("Bomb pot ante per player [10]: ", default=10)
    else:
        config["big_blind"] = ask_blinds()

    return config


def show_numbered_cards(cards):
    for index, card in enumerate(cards, start=1):
        print(f"  {index}: {card}")


def ask_card_indexes(prompt, available_indexes, count=2):
    while True:
        raw_value = prompt_input(prompt).strip()
        try:
            indexes = [int(part) for part in raw_value.replace(",", " ").split()]
        except ValueError:
            print("Use card numbers, like: 1 4")
            continue

        if len(indexes) != count:
            print(f"Choose exactly {count} cards.")
            continue

        if len(set(indexes)) != count:
            print("Do not use the same card twice.")
            continue

        if any(index not in available_indexes for index in indexes):
            print("Choose only from the cards still available.")
            continue

        return indexes


def ask_allocator_allocation(cards, top_board=None, bottom_board=None):
    available_indexes = set(range(1, len(cards) + 1))

    print("\nAllocation phase")
    print("-" * 60)
    if top_board is not None:
        print(f"Top board: {show_cards(top_board)}")
        print(f"Bottom board: {show_cards(bottom_board)}")

    print("Your cards:")
    show_numbered_cards(cards)

    top_indexes = ask_card_indexes("Top board cards: ", available_indexes)
    available_indexes -= set(top_indexes)

    bottom_indexes = ask_card_indexes("Bottom board cards: ", available_indexes)
    available_indexes -= set(bottom_indexes)

    hand_indexes = sorted(available_indexes)
    print(f"Hand strength cards: {' '.join(str(index) for index in hand_indexes)}")

    return top_indexes, bottom_indexes, hand_indexes


def format_winners(winners, label_key):
    return ", ".join(
        f"{winner['player']} ({winner[label_key]}, {winner['points']} point"
        f"{'' if winner['points'] == '1' else 's'})"
        for winner in winners
    )


def show_allocator_showdown(details):
    show_allocator_score_section(details)

    side_pots = details.get("side_pots", [])
    for side_pot in side_pots:
        print(f"\n{side_pot['name']} results")
        print(f"Pot amount: {side_pot['amount']}")
        show_allocator_score_section(side_pot)


def show_allocator_score_section(details):
    print("Top board")
    print(f"Board: {show_cards(details['top']['board'])}")
    print("Allocations:")
    for player, result in details["top"]["players"].items():
        print(
            f"  {player}: {show_cards(result['cards'])} "
            f"({result['hand_name']})"
        )
    print(f"Winners: {format_winners(details['top']['winners'], 'hand_name')}")

    print("\nBottom board")
    print(f"Board: {show_cards(details['bottom']['board'])}")
    print("Allocations:")
    for player, result in details["bottom"]["players"].items():
        print(
            f"  {player}: {show_cards(result['cards'])} "
            f"({result['hand_name']})"
        )
    print(f"Winners: {format_winners(details['bottom']['winners'], 'hand_name')}")

    print("\nHand strength")
    print("Allocations:")
    for player, result in details["hand_strength"]["players"].items():
        print(
            f"  {player}: {show_cards(result['cards'])} "
            f"({result['label']})"
        )
    print(
        "Winners: "
        f"{format_winners(details['hand_strength']['winners'], 'label')}"
    )

    print("\nTotal scores:")
    for player, total in details["totals"].items():
        print(f"  {player}: {total}")


class PokerClient:
    def __init__(self, host, port, name):
        self.host = host
        self.port = port
        self.name = name
        self.socket_obj = None

    def run(self):
        try:
            socket_obj = socket.create_connection(
                (self.host, self.port),
                timeout=TIMEOUTS["client_connect"],
            )
        except TimeoutError:
            print(f"Could not connect to {self.host}:{self.port}: timed out.")
            return
        except ConnectionRefusedError:
            print(f"Could not connect to {self.host}:{self.port}: connection refused.")
            return
        except OSError as error:
            print(f"Could not connect to {self.host}:{self.port}: {error}")
            return

        socket_obj.settimeout(None)
        with socket_obj:
            self.socket_obj = socket_obj
            set_disconnect_checker(self._server_disconnected)
            file_obj = socket_obj.makefile("rw", encoding="utf-8", newline="\n")
            print(f"Connected to {self.host}:{self.port}")

            try:
                while True:
                    try:
                        message = recv_json(file_obj)
                    except ProtocolError as error:
                        print(f"Server sent an invalid message: {error}")
                        return
                    except TimeoutError:
                        print("Timed out waiting for the server. Reconnect with the same name if needed.")
                        return
                    except ConnectionResetError:
                        print("Disconnected from server.")
                        return

                    if message is None:
                        print("Disconnected from server.")
                        return

                    try:
                        should_exit = self._handle_message(file_obj, message)
                    except ServerDisconnected:
                        return
                    except OSError:
                        print("Disconnected from server.")
                        return

                    if should_exit:
                        return
            finally:
                set_disconnect_checker(None)
                self.socket_obj = None

    def _server_disconnected(self):
        if self.socket_obj is None:
            return False

        try:
            readable, _, _ = select.select([self.socket_obj], [], [], 0)
            if not readable:
                return False

            data = self.socket_obj.recv(1, socket.MSG_PEEK)
            return data == b""
        except (BlockingIOError, InterruptedError):
            return False
        except (ConnectionResetError, OSError, ValueError):
            return True

    def _handle_message(self, file_obj, message):
        message_type = message.get("type")

        if message_type == "welcome":
            print(message["message"])

        elif message_type == "request_name":
            if self.name:
                name = self.name
                self.name = ""
            else:
                name = prompt_input("Player name: ").strip() or "Player"

            send_json(file_obj, {"type": "join", "name": name})

        elif message_type == "name_taken":
            print(message["message"])

        elif message_type == "joined":
            self.name = message["name"]
            print(f"Joined as {self.name}.")

        elif message_type == "request_lobby_action":
            action = ask_lobby_action()
            send_json(file_obj, {"type": "lobby_action", "action": action})

        elif message_type == "request_table_config":
            send_json(file_obj, ask_table_config())

        elif message_type == "table_created":
            print(f"\n{message['message']}")
            print(f"Table ID: {message['table_id']}")

        elif message_type == "request_table_id":
            table_id = prompt_input("Table ID: ").strip().upper()
            send_json(file_obj, {"type": "table_id", "table_id": table_id})

        elif message_type == "table_not_found":
            print(f"\n{message['message']}")

        elif message_type == "request_buy_in":
            amount = ask_buy_in()
            send_json(file_obj, {"type": "buy_in", "amount": amount})

        elif message_type == "request_seat":
            if "table" in message:
                show_table_drawing(message["table"])
            seat = ask_seat(message["available_seats"])
            send_json(file_obj, {"type": "seat_choice", "seat": seat})

        elif message_type == "seated":
            print(message["message"])

        elif message_type == "reserved":
            print(message["message"])

        elif message_type == "waiting":
            print(message["message"])

        elif message_type == "state":
            show_state(message["state"], message.get("table"))

        elif message_type == "message":
            print(f"\n{message['message']}")

        elif message_type == "disconnect_timer":
            print(f"{message['player']} reconnect timer: {message['seconds']}s")

        elif message_type == "request_action":
            print(f"\nTo call: {message['to_call']}")
            if "bet" in message["legal_actions"]:
                print(f"Minimum bet: {message['min_raise']}")
            elif "raise" in message["legal_actions"]:
                print(f"Minimum raise to: {message.get('min_raise_to', message['min_raise'])}")
            if message.get("max_bet") is not None and "bet" in message["legal_actions"]:
                print(f"Maximum bet: {message['max_bet']}")
            if message.get("max_raise_to") is not None and "raise" in message["legal_actions"]:
                print(f"Maximum raise to: {message['max_raise_to']}")
            action, amount = ask_action(message["legal_actions"])
            send_json(
                file_obj,
                {
                    "type": "action",
                    "action": action,
                    "amount": amount,
                },
            )

        elif message_type == "request_allocator_allocation":
            top, bottom, hand = ask_allocator_allocation(
                message["hand"],
                message.get("top_board"),
                message.get("bottom_board"),
            )
            send_json(
                file_obj,
                {
                    "type": "allocator_allocation",
                    "top": top,
                    "bottom": bottom,
                    "hand": hand,
                },
            )

        elif message_type == "error":
            print(f"\nError: {message['message']}")

        elif message_type == "showdown":
            print("\nShowdown")
            print("-" * 60)
            if message.get("allocator_details") is not None:
                show_allocator_showdown(message["allocator_details"])
            if message.get("hands"):
                print("Player hands:")
                for hand_info in message["hands"]:
                    hand_name = hand_info.get("hand_name", "unknown hand")
                    print(
                        f"  {hand_info['player']}: "
                        f"{show_cards(hand_info['hand'])} ({hand_name})"
                    )

            winner_hand_names = message.get("winner_hand_names", {})
            winner_text = ", ".join(
                f"{winner} ({winner_hand_names.get(winner, message['hand_name'])})"
                for winner in message["winners"]
            )
            if message.get("allocator_details") is None:
                print(f"Winners: {winner_text}")
                if message.get("top_board") is not None:
                    print(f"Top board: {show_cards(message['top_board'])}")
                    print(f"Bottom board: {show_cards(message['bottom_board'])}")
                else:
                    print(f"Board: {show_cards(message['board'])}")

            print("Amount won:")
            for name, amount in message["amount_won"].items():
                print(f"  {name}: {amount}")

        elif message_type == "request_continue":
            # Compatibility with older servers: continue without prompting.
            send_json(file_obj, {"type": "continue", "continue": True})

        elif message_type == "request_rebuy":
            print(f"\n{message.get('message', 'You are out of chips.')}")
            amount = ask_rebuy(message.get("default_amount", "1000"))
            send_json(
                file_obj,
                {
                    "type": "rebuy",
                    "rebuy": amount is not None,
                    "amount": amount or 0,
                },
            )

        elif message_type == "rebought":
            print(message.get("message", "Rebuy successful."))

        elif message_type == "session_over":
            print(message["message"])
            return True

        else:
            print(f"Unknown server message: {message}")

        return False


def main():
    parser = argparse.ArgumentParser(description="PokerMeow network client")
    parser.add_argument("host", help="Server IP address, for example 192.168.1.23")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--name", default="")
    args = parser.parse_args()

    name = args.name.strip()
    client = PokerClient(args.host, args.port, name)
    client.run()


if __name__ == "__main__":
    main()
