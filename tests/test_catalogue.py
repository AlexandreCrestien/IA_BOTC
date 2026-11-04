import pytest

from backend.models import Alignement, Effect, Equipe, Phase, TypeEffet
from backend.rules import ROLES, get_role


def test_six_roles_in_catalogue():
    assert set(ROLES) == {"Diablotin", "Empoisonneur", "Moine", "Voyante", "Détective", "Majordome"}


@pytest.mark.parametrize(
    "name, team, alignment",
    [
        ("Diablotin", Equipe.DEMON, Alignement.MAUVAIS),
        ("Empoisonneur", Equipe.SBIRE, Alignement.MAUVAIS),
        ("Moine", Equipe.VILLAGEOIS, Alignement.BON),
        ("Voyante", Equipe.VILLAGEOIS, Alignement.BON),
        ("Détective", Equipe.VILLAGEOIS, Alignement.BON),
        ("Majordome", Equipe.OUTSIDER, Alignement.BON),
    ],
)
def test_team_and_alignment(name, team, alignment):
    role = get_role(name)
    assert role.team == team
    assert role.alignment == alignment


def test_diablotin_kills_every_night():
    role = get_role("Diablotin")
    assert role.phase == Phase.NUIT and TypeEffet.TUE in role.effects


def test_empoisonneur_poisons_every_night():
    role = get_role("Empoisonneur")
    assert role.phase == Phase.NUIT and TypeEffet.EMPOISONNE in role.effects


def test_voyante_probes_every_night():
    role = get_role("Voyante")
    assert role.phase == Phase.NUIT and TypeEffet.SONDE in role.effects


def test_detective_does_not_act_at_night():
    role = get_role("Détective")
    assert role.phase is None and TypeEffet.SONDE in role.effects


def test_majordome_acts_at_night_without_direct_effect():
    role = get_role("Majordome")
    assert role.phase == Phase.NUIT and role.effects == ()


def test_poison_lasts_until_end_of_next_day():
    # Posé la nuit 1 : actif pendant le jour 1, retiré au début de la nuit 2.
    poison = Effect(
        type=TypeEffet.EMPOISONNE,
        source="Empoisonneur",
        turn_start=1,
        phase_start=Phase.NUIT,
        turn_end=2,
        phase_end=Phase.NUIT,
    )
    assert not poison.is_expired(1, Phase.DISCUSSION)
    assert poison.is_expired(2, Phase.NUIT)


def test_allowed_links_per_role():
    assert get_role("Majordome").allowed_links == ("maitre",)
    assert get_role("Voyante").allowed_links == ("fausse_piste",)
    assert get_role("Moine").allowed_links == ()