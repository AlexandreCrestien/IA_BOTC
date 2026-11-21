from backend.models import GameState, Phase, Player
from backend.rules import get_role, master_of, resolve_night


def make_player(id: str, role: str) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role))


def night_game() -> GameState:
    players = (
        make_player("a", "reaper"),
        make_player("b", "apothecary"),
        make_player("c", "watchman"),
        make_player("d", "medium"),
        make_player("e", "inquisitor"),
        make_player("f", "valet"),
    )
    return GameState(turn=1, phase=Phase.NIGHT, players=players)


def test_poisoned_valet_in_same_night_sets_no_master():
    state = resolve_night(night_game(), {"b": ("f",), "f": ("a",)})
    assert master_of(state, "f") is None


def test_unpoisoned_valet_sets_master_in_same_night():
    state = resolve_night(night_game(), {"f": ("a",)})
    assert master_of(state, "f") == "a"