import pytest
from pydantic import ValidationError

from backend.models import Alignment, Team, Role
from backend.rules import ROLES, get_role


def monk() -> Role:
    return get_role("monk")


def test_monk_is_in_catalogue():
    assert ROLES["monk"] == monk()


def test_unknown_role_refused():
    with pytest.raises(KeyError):
        get_role("Inexistant")


def test_monk_is_good():
    assert monk().alignment == Alignment.GOOD


def test_outsider_is_good():
    recluse = Role(name_FR="Recluse", name_EN="detective", team=Team.OUTSIDER)
    assert recluse.alignment == Alignment.GOOD


@pytest.mark.parametrize("team", [Team.MINION, Team.DEMON])
def test_minion_and_demon_are_evil(team):
    assert Role(name_FR="Test", name_EN="imp", team=team).alignment == Alignment.EVIL


def test_role_without_specific_phase():
    assert Role(name_FR="Recluse", name_EN="detective", team=Team.OUTSIDER).phase is None


def test_empty_name_refused():
    with pytest.raises(ValidationError):
        Role(name_FR="", name_EN="monk", team=Team.TOWNSFOLK)


def test_role_is_immutable():
    role = monk()
    with pytest.raises(ValidationError):
        role.name_FR = "autre"