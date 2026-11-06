import pytest

from backend.models import GameState, Phase, Player, TypeEffet
from backend.rules import get_role, poison


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


def test_poison_is_added_to_target():
    state = poison(night_game(), "b", "c")
    assert state.player("c").has_effect(TypeEffet.EMPOISONNE)


def test_poison_lasts_through_next_day():
    state = poison(night_game(turn=1), "b", "c")
    effect = state.player("c").effects[0]
    assert not effect.is_expired(1, Phase.DISCUSSION)
    assert effect.is_expired(2, Phase.NUIT)


def test_poisoner_cannot_target_himself():
    with pytest.raises(ValueError):
        poison(night_game(), "b", "b")


def test_poison_on_dead_target_is_refused():
    """skills/roles/poisoner.md : l'Empoisonneur doit choisir un joueur vivant."""
    state = night_game().replace_player(make_player("c", "monk", alive=False))
    with pytest.raises(ValueError):
        poison(state, "b", "c")


def test_poisoned_poisoner_has_no_effect():
    poisoned = make_player("b", "poisoner").add_effect(
        __import__("backend.models", fromlist=["Effect"]).Effect(
            type=TypeEffet.EMPOISONNE, source="x", turn_start=1, phase_start=Phase.NUIT,
        )
    )
    state = night_game().replace_player(poisoned)
    result = poison(state, "b", "c")
    assert not result.player("c").has_effect(TypeEffet.EMPOISONNE)