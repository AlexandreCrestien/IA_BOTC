from backend.models import GameState, Phase, Player
from backend.rules import get_role, resolve_night


def make_player(id: str, role: str) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role))


def night_game() -> GameState:
    return GameState(
        turn=1,
        phase=Phase.NUIT,
        players=(
            make_player("a", "imp"),
            make_player("b", "poisoner"),
            make_player("c", "monk"),
            make_player("d", "psychic"),
            make_player("e", "detective"),
            make_player("f", "butler"),
        ),
    )


def test_kill_applies():
    state = resolve_night(night_game(), {"a": ("c",)})
    assert not state.player("c").alive


def test_protection_blocks_kill():
    state = resolve_night(night_game(), {"c": ("f",), "a": ("f",)})
    assert state.player("f").alive


def test_poisoned_monk_does_not_protect():
    state = resolve_night(night_game(), {"b": ("c",), "c": ("f",), "a": ("f",)})
    assert not state.player("f").alive


def test_poisoned_imp_kills_nothing():
    state = resolve_night(night_game(), {"b": ("a",), "a": ("c",)})
    assert state.player("c").alive


def test_no_choice_no_change():
    state = night_game()
    assert resolve_night(state, {}) == state

def test_butler_killed_tonight_does_not_choose_a_master():
    """Régression : le Diablotin tue le Majordome avant son tour ; la partie ne doit pas planter."""
    state = resolve_night(night_game(), {"a": ("f",), "f": ("b",)})
    assert not state.player("f").alive
    assert "maitre" not in state.player("f").links
