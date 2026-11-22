import pytest

from backend.models import Effect, GameState, Phase, Player, EffectType
from backend.rules import get_role, kill, protect


def make_player(id: str, role: str, alive: bool = True) -> Player:
    p = Player(id=id, name=id.upper(), role=get_role(role))
    return p if alive else p.die()


def night_game(turn: int = 1) -> GameState:
    return GameState(
        turn=turn,
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


poisoned = Effect(type=EffectType.POISONED, source="apothecary", turn_start=1, phase_start=Phase.NIGHT)


def test_protection_is_added_to_target():
    state = protect(night_game(), "c", "f")
    assert state.player("f").has_effect(EffectType.PROTECTED)


def test_protection_ends_at_start_of_day():
    state = protect(night_game(turn=1), "c", "f")
    effect = state.player("f").effects[0]
    assert not effect.is_expired(1, Phase.NIGHT)
    assert effect.is_expired(1, Phase.DISCUSSION)


def test_watchman_cannot_protect_himself():
    with pytest.raises(ValueError):
        protect(night_game(), "c", "c")


def test_kill_kills_target():
    state = kill(night_game(), "a", "c")
    assert not state.player("c").alive


def test_protection_blocks_kill():
    state = protect(night_game(), "c", "f")
    state = kill(state, "a", "f")
    assert state.player("f").alive


def test_kill_on_dead_target_has_no_effect():
    state = night_game().replace_player(make_player("c", "watchman", alive=False))
    assert kill(state, "a", "c") == state


def test_poisoned_reaper_kills_nothing():
    state = night_game().replace_player(make_player("a", "reaper").add_effect(poisoned))
    assert kill(state, "a", "c").player("c").alive


def test_poisoned_watchman_protects_nothing():
    state = night_game().replace_player(make_player("c", "watchman").add_effect(poisoned))
    state = protect(state, "c", "f")
    assert not state.player("f").has_effect(EffectType.PROTECTED)