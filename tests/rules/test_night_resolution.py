from backend.models import GameState, Phase, Player
from backend.rules import get_role, resolve_night


def make_player(id: str, role: str) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role))


def night_game() -> GameState:
    return GameState(
        turn=1,
        phase=Phase.NIGHT,
        players=(
            make_player("a", "reaper"),
            make_player("b", "apothecary"),
            make_player("c", "watchman"),
            make_player("d", "medium"),
            make_player("e", "inquisitor"),
            make_player("f", "valet"),
        ),
    )


def test_kill_applies():
    state = resolve_night(night_game(), {"a": ("c",)})
    assert not state.player("c").alive


def test_protection_blocks_kill():
    state = resolve_night(night_game(), {"c": ("f",), "a": ("f",)})
    assert state.player("f").alive


def test_poisoned_watchman_does_not_protect():
    state = resolve_night(night_game(), {"b": ("c",), "c": ("f",), "a": ("f",)})
    assert not state.player("f").alive


def test_poisoned_reaper_kills_nothing():
    state = resolve_night(night_game(), {"b": ("a",), "a": ("c",)})
    assert state.player("c").alive


def test_no_choice_no_change():
    state = night_game()
    assert resolve_night(state, {}) == state