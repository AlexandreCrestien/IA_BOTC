import pytest
from pydantic import ValidationError

from backend.models import Effect, Equipe, Phase, Player, Role, TypeEffet
from backend.rules import get_role


def player(**kwargs) -> Player:
    base = dict(id="j1", name="Odette", role=get_role("monk"))
    base.update(kwargs)
    return Player(**base)


def protection() -> Effect:
    return Effect(
        type=TypeEffet.PROTEGE,
        source="monk",
        turn_start=2,
        phase_start=Phase.NUIT,
        turn_end=2,
        phase_end=Phase.DISCUSSION,
    )


def test_alive_by_default():
    p = player()
    assert p.alive and not p.ghost_vote and p.effects == ()


def test_monk_can_act_when_alive():
    assert player().can_act


def test_dead_player_cannot_act():
    assert not player().die().can_act


def test_role_without_phase_cannot_act():
    assert not player(role=Role(name_FR="Recluse", name_EN="hermit", team=Equipe.OUTSIDER)).can_act


def test_used_power_blocks_action():
    assert not player(power_used=True).can_act


def test_dead_player_keeps_ghost_vote():
    p = player().die()
    assert not p.alive and p.ghost_vote and p.can_vote


def test_ghost_vote_used_only_once():
    p = player().die().use_ghost_vote()
    assert not p.can_vote


def test_dying_twice_refused():
    with pytest.raises(ValueError):
        player().die().die()


def test_ghost_vote_refused_if_alive():
    with pytest.raises(ValueError):
        player().use_ghost_vote()


def test_add_effect_does_not_modify_original():
    original = player()
    new = original.add_effect(protection())
    assert original.effects == () and new.has_effect(TypeEffet.PROTEGE)


def test_remove_expired_effects_keeps_active_ones():
    active = Effect(type=TypeEffet.EMPOISONNE, source="Test", turn_start=1, phase_start=Phase.NUIT)
    p = player().add_effect(protection()).add_effect(active)
    p = p.remove_expired_effects(2, Phase.DISCUSSION)
    assert not p.has_effect(TypeEffet.PROTEGE) and p.has_effect(TypeEffet.EMPOISONNE)


def test_player_is_immutable():
    with pytest.raises(ValidationError):
        player().name = "autre"


def test_empty_name_refused():
    with pytest.raises(ValidationError):
        player(name="")


def test_links_empty_by_default():
    assert player().links == {}


def test_with_link_does_not_modify_original():
    original = player()
    new = original.with_link("maitre", "odette")
    assert original.links == {} and new.link("maitre") == "odette"