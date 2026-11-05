import pytest

from backend.models import Effect, GameState, Phase, Player, TypeEffet
from backend.rules import get_role, kill, protect


def make_player(id: str, role: str, alive: bool = True) -> Player:
    p = Player(id=id, name=id.upper(), role=get_role(role))
    return p if alive else p.die()


def night_game(turn: int = 1) -> GameState:
    return GameState(
        turn=turn,
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


poisoned = Effect(type=TypeEffet.EMPOISONNE, source="poisoner", turn_start=1, phase_start=Phase.NUIT)


def test_protection_is_added_to_target():
    state = protect(night_game(), "c", "f")
    assert state.player("f").has_effect(TypeEffet.PROTEGE)


def test_protection_ends_at_start_of_day():
    state = protect(night_game(turn=1), "c", "f")
    effect = state.player("f").effects[0]
    assert not effect.is_expired(1, Phase.NUIT)
    assert effect.is_expired(1, Phase.DISCUSSION)


def test_monk_cannot_protect_himself():
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
    state = night_game().replace_player(make_player("c", "monk", alive=False))
    assert kill(state, "a", "c") == state


def test_poisoned_imp_kills_nothing():
    state = night_game().replace_player(make_player("a", "imp").add_effect(poisoned))
    assert kill(state, "a", "c").player("c").alive


def test_poisoned_monk_protects_nothing():
    state = night_game().replace_player(make_player("c", "monk").add_effect(poisoned))
    state = protect(state, "c", "f")
    assert not state.player("f").has_effect(TypeEffet.PROTEGE)