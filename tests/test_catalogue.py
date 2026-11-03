import pytest

from backend.models import Alignement, Effet, Equipe, Phase, TypeEffet
from backend.rules_engine import ROLES, obtenir_role


def test_six_roles_dans_le_catalogue():
    assert set(ROLES) == {"Diablotin", "Empoisonneur", "Moine", "Voyante", "Détective", "Majordome"}


@pytest.mark.parametrize(
    "nom, camp, alignement",
    [
        ("Diablotin", Equipe.DEMON, Alignement.MAUVAIS),
        ("Empoisonneur", Equipe.SBIRE, Alignement.MAUVAIS),
        ("Moine", Equipe.VILLAGEOIS, Alignement.BON),
        ("Voyante", Equipe.VILLAGEOIS, Alignement.BON),
        ("Détective", Equipe.VILLAGEOIS, Alignement.BON),
        ("Majordome", Equipe.OUTSIDER, Alignement.BON),
    ],
)
def test_camp_et_alignement(nom, camp, alignement):
    r = obtenir_role(nom)
    assert r.camp == camp
    assert r.alignement == alignement


def test_diablotin_tue_chaque_nuit():
    r = obtenir_role("Diablotin")
    assert r.phase == Phase.NUIT and TypeEffet.TUE in r.effets


def test_empoisonneur_empoisonne_chaque_nuit():
    r = obtenir_role("Empoisonneur")
    assert r.phase == Phase.NUIT and TypeEffet.EMPOISONNE in r.effets


def test_voyante_sonde_chaque_nuit():
    r = obtenir_role("Voyante")
    assert r.phase == Phase.NUIT and TypeEffet.SONDE in r.effets


def test_detective_n_agit_pas_la_nuit():
    r = obtenir_role("Détective")
    assert r.phase is None and TypeEffet.SONDE in r.effets


def test_majordome_agit_la_nuit_sans_effet_direct():
    r = obtenir_role("Majordome")
    assert r.phase == Phase.NUIT and r.effets == ()


def test_poison_dure_jusqu_a_la_fin_de_la_journee_suivante():
    # Posé la nuit 1 : actif pendant le jour 1, retiré au début de la nuit 2.
    poison = Effet(
        type=TypeEffet.EMPOISONNE,
        source="Empoisonneur",
        tour_debut=1,
        phase_debut=Phase.NUIT,
        tour_fin=2,
        phase_fin=Phase.NUIT,
    )
    assert not poison.est_expire(1, Phase.DISCUSSION)
    assert poison.est_expire(2, Phase.NUIT)



def test_liens_autorises_par_role():
    assert obtenir_role("Majordome").liens_autorises == ("maitre",)
    assert obtenir_role("Voyante").liens_autorises == ("fausse_piste",)
    assert obtenir_role("Moine").liens_autorises == ()