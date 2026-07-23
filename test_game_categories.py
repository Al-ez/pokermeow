from allocator import AllocatorGame
from game_categories import BoardCategory
from nlh import NoLimitHoldemGame
from plo import PotLimitOmahaGame


def test_nlh_is_a_single_board_game():
    assert NoLimitHoldemGame.board_category is BoardCategory.SINGLE_BOARD


def test_plo_is_a_single_board_game():
    assert PotLimitOmahaGame.board_category is BoardCategory.SINGLE_BOARD


def test_allocator_is_a_double_board_game():
    assert AllocatorGame.board_category is BoardCategory.DOUBLE_BOARD


def test_board_categories_have_protocol_friendly_values():
    assert BoardCategory.SINGLE_BOARD.value == "single_board"
    assert BoardCategory.DOUBLE_BOARD.value == "double_board"
