from backend.models import GameState, Phase, Player
from backend.rules import get_role, master_of, resolve_night


def make_player(id: str, role: str) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role))


def night_game() -> GameState:
    players = (
        make_player("a", "imp"),
        make_player("b", "poisoner"),
        make_player("c", "monk"),
        make_player("d", "psychic"),
        make_player("e", "detective"),
        make_player("f", "butler"),
    )
    return GameState(turn=1, phase=Phase.NUIT, players=players)


def test_poisoned_butler_in_same_night_sets_no_master():
    state = resolve_night(night_game(), {"b": ("f",), "f": ("a",)})
    assert master_of(state, "f") is None


def test_unpoisoned_butler_sets_master_in_same_night():
    state = resolve_night(night_game(), {"f": ("a",)})
    assert master_of(state, "f") == "a"