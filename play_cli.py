from decimal import Decimal, InvalidOperation

from allocator import AllocatorGame
from nlh import NoLimitHoldemGame
from plo import PotLimitOmahaGame


def show_cards(cards):
    return ", ".join(str(card) for card in cards)


def show_table(game, hero_name):
    state = game.table_state()
    hero = state["players"][hero_name]

    print("\n" + "=" * 60)
    print(f"Pot: {state['pot']}")
    if "top_board" in state:
        top_board = show_cards(state["top_board"]) if state["top_board"] else "(empty)"
        bottom_board = show_cards(state["bottom_board"]) if state["bottom_board"] else "(empty)"
        print(f"Top board: {top_board}")
        print(f"Bottom board: {bottom_board}")
    else:
        print(f"Board: {show_cards(state['board']) if state['board'] else '(empty)'}")
    print(f"Your hand: {show_cards(hero['hand'])}")
    print("-" * 60)

    for name, player in state["players"].items():
        status = []
        if player["folded"]:
            status.append("folded")
        if player["all_in"]:
            status.append("all-in")

        status_text = f" ({', '.join(status)})" if status else ""
        hand_text = show_cards(player["hand"]) if name == hero_name else "[hidden]"

        print(
            f"{name}: stack={player['stack']} "
            f"bet={player['current_bet']} "
            f"committed={player['total_committed']} "
            f"hand={hand_text}{status_text}"
        )


def ask_int(prompt):
    while True:
        value = input(prompt).strip()

        try:
            amount = int(value)
        except ValueError:
            print("Please enter a whole number.")
            continue

        if amount < 0:
            print("Please enter zero or more.")
            continue

        return amount


def ask_money(prompt):
    while True:
        value = input(prompt).strip()

        try:
            amount = Decimal(value)
            if not amount.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            print("Please enter a valid number.")
            continue

        if amount < 0:
            print("Please enter zero or more.")
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

        choice = input("Blinds: ").strip()
        for key, _, big_blind in options:
            if choice == key:
                return big_blind / Decimal("2"), big_blind

        print("Please choose 1 through 7.")


def ask_action(game, hero_name):
    legal = game.legal_actions(hero_name)

    while True:
        print(f"\nLegal actions: {', '.join(legal)}")
        action = input("Your action: ").strip().lower()

        if action not in legal:
            print("That action is not legal right now.")
            continue

        amount = 0
        if action in {"bet", "raise"}:
            limit_text = ""
            if action == "bet" and hasattr(game, "max_bet"):
                limit_text = f" (max {game.max_bet(hero_name)})"
            elif action == "raise" and hasattr(game, "max_raise_total"):
                limit_text = f" (max total bet {game.max_raise_total(hero_name)})"

            amount = ask_money(f"Amount{limit_text}: ")

        return action, amount


def bot_action(game, bot_name):
    legal = game.legal_actions(bot_name)

    if hasattr(game, "max_bet") and "bet" in legal:
        return "bet", game.max_bet(bot_name)

    if hasattr(game, "max_raise_total") and "raise" in legal:
        return "raise", game.max_raise_total(bot_name)

    if is_allocator_game(game) and "bet" in legal:
        player = game._player_by_name(bot_name)
        return "bet", min(player.stack, max(game.big_blind, game.pot))

    if is_allocator_game(game) and "raise" in legal:
        player = game._player_by_name(bot_name)
        to_call = game.current_bet - player.current_bet
        pot_after_call = game.pot + to_call
        pot_raise_total = game.current_bet + pot_after_call
        affordable_total = player.current_bet + player.stack
        return "raise", min(pot_raise_total, affordable_total)

    if "check" in legal:
        return "check", 0

    if "call" in legal:
        return "call", 0

    return "fold", 0


def describe_action(result):
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


def run_betting_round(game, hero_name):
    acted_players = set()

    while True:
        active_players = [
            player
            for player in game.players
            if not player.folded and not player.all_in
        ]

        if len(game.active_players()) <= 1:
            return

        if not active_players:
            return

        round_complete = True
        for player in active_players:
            if player.current_bet != game.current_bet:
                round_complete = False
                break

            if player.name not in acted_players:
                round_complete = False
                break

        if round_complete:
            return

        player = game.players[game.action_index]

        if player.folded or player.all_in:
            game.action_index = game._next_active_index(game.action_index)
            continue

        if player.name == hero_name:
            show_table(game, hero_name)
            action, amount = ask_action(game, hero_name)
        else:
            action, amount = bot_action(game, player.name)

        result = game.act(player.name, action, amount)
        print(f"\n{describe_action(result)}")
        acted_players.add(player.name)

        if action in {"bet", "raise", "all_in"} and game.current_bet > 0:
            acted_players = {player.name}


def players_with_stack_behind(game):
    return [
        player
        for player in game.active_players()
        if not player.all_in and player.stack > 0
    ]


def should_skip_to_showdown(game):
    return len(game.active_players()) > 1 and len(players_with_stack_behind(game)) <= 1


def deal_remaining_board(game):
    if len(game.board) < 3:
        game.deal_flop()
        print("\nFlop dealt.")

    if len(game.board) < 4:
        game.deal_turn()
        print("\nTurn dealt.")

    if len(game.board) < 5:
        game.deal_river()
        print("\nRiver dealt.")


def is_allocator_game(game):
    return isinstance(game, AllocatorGame)


def show_numbered_cards(cards):
    for index, card in enumerate(cards, start=1):
        print(f"  {index}: {card}")


def ask_card_indexes(prompt, available_indexes, count=2):
    while True:
        raw_value = input(prompt).strip()
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


def ask_allocator_allocation(game, hero_name):
    hero = game._player_by_name(hero_name)
    available_indexes = set(range(1, len(hero.hand) + 1))

    print("\nAllocation phase")
    print("-" * 60)
    print("Your cards:")
    show_numbered_cards(hero.hand)

    top_indexes = ask_card_indexes("Top board cards: ", available_indexes)
    available_indexes -= set(top_indexes)

    bottom_indexes = ask_card_indexes("Bottom board cards: ", available_indexes)
    available_indexes -= set(bottom_indexes)

    hand_indexes = sorted(available_indexes)
    print(f"Hand strength cards: {' '.join(str(index) for index in hand_indexes)}")

    game.set_allocation(
        hero_name,
        [hero.hand[index - 1] for index in top_indexes],
        [hero.hand[index - 1] for index in bottom_indexes],
        [hero.hand[index - 1] for index in hand_indexes],
    )


def allocate_bots(game, hero_name):
    for player in game.active_players():
        if player.name == hero_name:
            continue

        game.set_allocation(
            player.name,
            player.hand[0:2],
            player.hand[2:4],
            player.hand[4:6],
        )
        print(f"{player.name} allocates cards.")


def allocator_showdown_setup(game, hero_name):
    if len(game.active_players()) <= 1:
        return

    if any(player.name == hero_name for player in game.active_players()):
        ask_allocator_allocation(game, hero_name)

    allocate_bots(game, hero_name)

    scores = game.calculate_scores()
    print("\nAllocator scores")
    print("-" * 60)
    for player_name, score in scores.items():
        print(
            f"{player_name}: total={score.total} "
            f"top={score.top_board_points} "
            f"bottom={score.bottom_board_points} "
            f"hand={score.hand_strength_points}"
        )


def play_allocator_hand(game, hero_name):
    game.start_hand()

    print("\nNew Allocator bomb pot started.")
    if game.bomb_pot_ante > 0:
        print(f"Each player antes {game.bomb_pot_ante}.")

    if len(game.active_players()) > 1:
        game.deal_flop()
        print("\nFlops dealt.")
        run_betting_round(game, hero_name)

    if len(game.active_players()) > 1:
        if should_skip_to_showdown(game):
            deal_remaining_board(game)
        elif len(game.board) == 3:
            game.deal_turn()
            print("\nTurns dealt.")
            run_betting_round(game, hero_name)

    if len(game.active_players()) > 1:
        if should_skip_to_showdown(game):
            deal_remaining_board(game)
        elif len(game.board) == 4:
            game.deal_river()
            print("\nRivers dealt.")
            run_betting_round(game, hero_name)

    if len(game.active_players()) > 1 and len(game.board) < 5:
        deal_remaining_board(game)

    show_table(game, hero_name)
    allocator_showdown_setup(game, hero_name)
    result = game.showdown()

    print("\nShowdown result")
    print("-" * 60)
    print(f"Winners: {', '.join(result.winners)}")
    print("Amount won:")
    for name, amount in result.amount_won.items():
        print(f"  {name}: {amount}")

    game.advance_dealer()


def play_hand(game, hero_name):
    if is_allocator_game(game):
        play_allocator_hand(game, hero_name)
        return

    game.start_hand()

    print("\nNew hand started.")
    run_betting_round(game, hero_name)

    if len(game.active_players()) > 1 and should_skip_to_showdown(game):
        deal_remaining_board(game)
    elif len(game.active_players()) > 1:
        game.deal_flop()
        print("\nFlop dealt.")
        if should_skip_to_showdown(game):
            deal_remaining_board(game)
        else:
            run_betting_round(game, hero_name)

    if len(game.active_players()) > 1 and len(game.board) == 3:
        if should_skip_to_showdown(game):
            deal_remaining_board(game)
        else:
            game.deal_turn()
            print("\nTurn dealt.")
            if should_skip_to_showdown(game):
                deal_remaining_board(game)
            else:
                run_betting_round(game, hero_name)

    if len(game.active_players()) > 1 and len(game.board) == 4:
        if should_skip_to_showdown(game):
            deal_remaining_board(game)
        else:
            game.deal_river()
            print("\nRiver dealt.")
            if not should_skip_to_showdown(game):
                run_betting_round(game, hero_name)

    if len(game.active_players()) > 1 and len(game.board) < 5:
        deal_remaining_board(game)

    show_table(game, hero_name)
    result = game.showdown()

    print("\nShowdown result")
    print("-" * 60)
    print(f"Winners: {', '.join(result.winners)}")
    print(f"Winning hand: {result.hand_name}")

    if result.winning_cards:
        print(f"Winning cards: {show_cards(result.winning_cards)}")

    print("Amount won:")
    for name, amount in result.amount_won.items():
        print(f"  {name}: {amount}")

    game.advance_dealer()


def main():
    print("Poker CLI")
    print("=" * 60)

    game_choice = input("Choose game: [1] NLH  [2] PLO  [3] Allocator: ").strip()
    if game_choice == "2":
        game_class = PotLimitOmahaGame
        game_name = "Pot-Limit Omaha"
    elif game_choice == "3":
        game_class = AllocatorGame
        game_name = "Allocator"
    else:
        game_class = NoLimitHoldemGame
        game_name = "No-Limit Texas Hold'em"

    print(f"\nStarting {game_name}")

    hero_name = input("Your player name: ").strip() or "Hero"
    bot_count = ask_int("Number of bots: ")

    if bot_count < 1:
        print("You need at least one bot to play.")
        bot_count = 1

    starting_stack = ask_money("Starting stack: ")
    if starting_stack <= 0:
        starting_stack = 1000

    bomb_pot_ante = 0
    if game_class is AllocatorGame:
        small_blind = 1
        big_blind = 2
        bomb_pot_ante = ask_int("Bomb pot ante per player: ")
        while bomb_pot_ante <= 0:
            print("Bomb pot ante must be greater than zero.")
            bomb_pot_ante = ask_int("Bomb pot ante per player: ")
    else:
        small_blind, big_blind = ask_blinds()

    player_stacks = {hero_name: starting_stack}
    for index in range(1, bot_count + 1):
        player_stacks[f"Bot {index}"] = starting_stack

    if game_class is AllocatorGame:
        game = game_class(
            player_stacks,
            small_blind=small_blind,
            big_blind=big_blind,
            shuffle=True,
            bomb_pot_ante=bomb_pot_ante,
        )
    else:
        game = game_class(
            player_stacks,
            small_blind=small_blind,
            big_blind=big_blind,
            shuffle=True,
        )

    while True:
        play_hand(game, hero_name)

        state = game.table_state()
        hero_stack = state["players"][hero_name]["stack"]
        bot_stacks = [
            player["stack"]
            for name, player in state["players"].items()
            if name != hero_name
        ]

        if hero_stack <= 0:
            print("\nYou are out of chips.")
            break

        if all(stack <= 0 for stack in bot_stacks):
            print("\nYou won all the chips.")
            break

        again = input("\nPlay another hand? [y/n]: ").strip().lower()
        if again != "y":
            break

    print("\nThanks for playing.")


if __name__ == "__main__":
    main()
