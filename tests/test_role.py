import pytest
from pydantic import ValidationError

from backend.models import Alignement, Equipe, Phase, Role
from backend.rules import ROLES, get_role


def monk() -> Role:
    return get_role("monk")


def test_monk_is_in_catalogue():
    assert ROLES["monk"] == monk()


def test_unknown_role_refused():
    with pytest.raises(KeyError):
        get_role("Inexistant")


def test_monk_is_good():
    assert monk().alignment == Alignement.BON


def test_outsider_is_good():
    recluse = Role(name="Recluse", team=Equipe.OUTSIDER)
    assert recluse.alignment == Alignement.BON


@pytest.mark.parametrize("team", [Equipe.SBIRE, Equipe.DEMON])
def test_minion_and_demon_are_evil(team):
    assert Role(name="Test", team=team).alignment == Alignement.MAUVAIS


def test_role_without_specific_phase():
    assert Role(name="Recluse", team=Equipe.OUTSIDER).phase is None


def test_effects_empty_by_default():
    assert Role(name="Recluse", team=Equipe.OUTSIDER).effects == ()


def test_empty_name_refused():
    with pytest.raises(ValidationError):
        Role(name="", team=Equipe.VILLAGEOIS)


def test_role_is_immutable():
    role = monk()
    with pytest.raises(ValidationError):
        role.name = "autre"