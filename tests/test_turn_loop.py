import random

import pytest

from backend.game_engine import play_game, play_turn
from backend.models import Alignement, GameState, Phase, Player
from backend.rules import get_role, winner


def make_player(id: str, role: str, **kwargs) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role), **kwargs)


def full_game() -> GameState:
    players = (
        make_player("a", "imp"),
        make_player("b", "poisoner"),
        make_player("c", "monk"),
        make_player("d", "psychic"),
        make_player("e", "detective"),
        make_player("f", "butler"),
    )
    return GameState(turn=2, phase=Phase.NUIT, players=players, channels=(), log=())


def test_turn_without_death_moves_to_next_night():
    result = play_turn(full_game(), random.Random(1), vote_choose=lambda s, pid: None)
    assert result.game_winner is None
    assert result.state.phase == Phase.NUIT
    assert result.state.turn == 3


def test_turn_requires_night_phase():
    state = full_game()
    state = GameState(turn=2, phase=Phase.VOTE, players=state.players, channels=(), log=())
    with pytest.raises(ValueError):
        play_turn(state, random.Random(1))


def test_executing_the_demon_gives_good_the_win():
    final = play_game(full_game(), random.Random(1), vote_choose=lambda s, pid: "a")
    assert winner(final) == Alignement.BON


def test_game_without_execution_stops_after_max_turns():
    with pytest.raises(RuntimeError):
        play_game(full_game(), random.Random(1), vote_choose=lambda s, pid: None, max_turns=3)