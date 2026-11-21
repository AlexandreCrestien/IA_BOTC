import pytest
from pydantic import ValidationError

from backend.models import Alignment, Team, Role
from backend.rules import ROLES, get_role


def watchman() -> Role:
    return get_role("watchman")


def test_watchman_is_in_catalogue():
    assert ROLES["watchman"] == watchman()


def test_unknown_role_refused():
    with pytest.raises(KeyError):
        get_role("Inexistant")


def test_watchman_is_good():
    assert watchman().alignment == Alignment.GOOD


def test_outsider_is_good():
    recluse = Role(name_FR="Recluse", name_EN="inquisitor", team=Team.OUTCAST)
    assert recluse.alignment == Alignment.GOOD


@pytest.mark.parametrize("team", [Team.ACCOMPLICE, Team.DEMON])
def test_accomplice_and_demon_are_evil(team):
    assert Role(name_FR="Test", name_EN="reaper", team=team).alignment == Alignment.EVIL


def test_role_without_specific_phase():
    assert Role(name_FR="Recluse", name_EN="inquisitor", team=Team.OUTCAST).phase is None


def test_empty_name_refused():
    with pytest.raises(ValidationError):
        Role(name_FR="", name_EN="watchman", team=Team.TOWNSFOLK)


def test_role_is_immutable():
    role = watchman()
    with pytest.raises(ValidationError):
        role.name_FR = "autre"