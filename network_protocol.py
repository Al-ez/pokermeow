import json
from decimal import Decimal


class ProtocolError(ValueError):
    pass


def json_default(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def send_json(file_obj, message):
    file_obj.write(json.dumps(message, default=json_default) + "\n")
    file_obj.flush()


def recv_json(file_obj):
    line = file_obj.readline()
    if not line:
        return None

    try:
        message = json.loads(line)
    except json.JSONDecodeError as error:
        raise ProtocolError("Malformed JSON message") from error

    if not isinstance(message, dict):
        raise ProtocolError("Protocol message must be a JSON object")

    return message


def card_text(card):
    return str(card)


def cards_text(cards):
    return [card_text(card) for card in cards]


def player_public_state(player):
    return {
        "name": player.name,
        "stack": player.stack,
        "folded": player.folded,
        "all_in": player.all_in,
        "current_bet": player.current_bet,
        "total_committed": player.total_committed,
        "hand_size": len(player.hand),
    }


def player_private_state(player):
    state = player_public_state(player)
    state["hand"] = cards_text(player.hand)
    return state


def visible_state_for(game, player_name):
    players = {}
    for player in game.players:
        if player.name == player_name:
            players[player.name] = player_private_state(player)
        else:
            players[player.name] = player_public_state(player)

    state = {
        "pot": game.pot,
        "board": cards_text(game.board),
        "current_bet": game.current_bet,
        "dealer": game.players[game.dealer_index].name,
        "players": players,
    }

    if hasattr(game, "top_board"):
        state["top_board"] = cards_text(game.top_board)
        state["bottom_board"] = cards_text(game.bottom_board)

    return state
