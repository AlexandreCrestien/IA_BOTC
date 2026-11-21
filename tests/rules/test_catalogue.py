import pytest

from backend.models import Alignment, Effect, Team, Phase, EffectType
from backend.rules import ROLES, get_role


def test_six_roles_in_catalogue():
    assert set(ROLES) == {"imp", "poisoner", "monk", "psychic", "detective", "butler"}


@pytest.mark.parametrize(
    "name, team, alignment",
    [
        ("imp", Team.DEMON, Alignment.EVIL),
        ("poisoner", Team.MINION, Alignment.EVIL),
        ("monk", Team.TOWNSFOLK, Alignment.GOOD),
        ("psychic", Team.TOWNSFOLK, Alignment.GOOD),
        ("detective", Team.TOWNSFOLK, Alignment.GOOD),
        ("butler", Team.OUTSIDER, Alignment.GOOD),
    ],
)
def test_team_and_alignment(name, team, alignment):
    role = get_role(name)
    assert role.team == team
    assert role.alignment == alignment


def test_diablotin_kills_every_night():
    role = get_role("imp")
    assert role.phase == Phase.NIGHT


def test_empoisonneur_poisons_every_night():
    role = get_role("poisoner")
    assert role.phase == Phase.NIGHT


def test_voyante_probes_every_night():
    role = get_role("psychic")
    assert role.phase == Phase.NIGHT


def test_detective_does_not_act_at_night():
    role = get_role("detective")
    assert role.phase is None


def test_majordome_acts_at_night_without_direct_effect():
    role = get_role("butler")
    assert role.phase == Phase.NIGHT


def test_poison_lasts_until_end_of_next_day():
    # Posé la nuit 1 : actif pendant le jour 1, retiré au début de la nuit 2.
    poison = Effect(
        type=EffectType.POISONED,
        source="poisoner",
        turn_start=1,
        phase_start=Phase.NIGHT,
        turn_end=2,
        phase_end=Phase.NIGHT,
    )
    assert not poison.is_expired(1, Phase.DISCUSSION)
    assert poison.is_expired(2, Phase.NIGHT)


def test_allowed_links_per_role():
    assert get_role("butler").allowed_links == ("master",)
    assert get_role("psychic").allowed_links == ("false_lead",)
    assert get_role("monk").allowed_links == ()