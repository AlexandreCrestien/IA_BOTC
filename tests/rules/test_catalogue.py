import pytest

from backend.models import Alignment, Effect, Team, Phase, EffectType
from backend.rules import ROLES, get_role


def test_six_roles_in_catalogue():
    assert set(ROLES) == {"reaper", "apothecary", "watchman", "medium", "inquisitor", "valet"}


@pytest.mark.parametrize(
    "name, team, alignment",
    [
        ("reaper", Team.DEMON, Alignment.EVIL),
        ("apothecary", Team.ACCOMPLICE, Alignment.EVIL),
        ("watchman", Team.TOWNSFOLK, Alignment.GOOD),
        ("medium", Team.TOWNSFOLK, Alignment.GOOD),
        ("inquisitor", Team.TOWNSFOLK, Alignment.GOOD),
        ("valet", Team.OUTCAST, Alignment.GOOD),
    ],
)
def test_team_and_alignment(name, team, alignment):
    role = get_role(name)
    assert role.team == team
    assert role.alignment == alignment


def test_reaper_kills_every_night():
    role = get_role("reaper")
    assert role.phase == Phase.NIGHT


def test_apothecary_poisons_every_night():
    role = get_role("apothecary")
    assert role.phase == Phase.NIGHT


def test_medium_probes_every_night():
    role = get_role("medium")
    assert role.phase == Phase.NIGHT


def test_inquisitor_does_not_act_at_night():
    role = get_role("inquisitor")
    assert role.phase is None


def test_valet_acts_at_night_without_direct_effect():
    role = get_role("valet")
    assert role.phase == Phase.NIGHT


def test_poison_lasts_until_end_of_next_day():
    # Posé la nuit 1 : actif pendant le jour 1, retiré au début de la nuit 2.
    poison = Effect(
        type=EffectType.POISONED,
        source="apothecary",
        turn_start=1,
        phase_start=Phase.NIGHT,
        turn_end=2,
        phase_end=Phase.NIGHT,
    )
    assert not poison.is_expired(1, Phase.DISCUSSION)
    assert poison.is_expired(2, Phase.NIGHT)


def test_allowed_links_per_role():
    assert get_role("valet").allowed_links == ("master",)
    assert get_role("medium").allowed_links == ("false_lead",)
    assert get_role("watchman").allowed_links == ()