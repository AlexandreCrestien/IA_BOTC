import random

import pytest

from backend.models import Alignement
from backend.rules_engine import ROLES_PARTIE_6, choisir_fausse_piste, distribuer_roles

IDS = ["j1", "j2", "j3", "j4", "j5", "j6"]


def test_chaque_role_une_seule_fois():
    roles = distribuer_roles(IDS, random.Random(1))
    assert sorted(r.nom for r in roles.values()) == sorted(ROLES_PARTIE_6)


def test_chaque_joueur_a_un_role():
    roles = distribuer_roles(IDS, random.Random(1))
    assert set(roles) == set(IDS)


def test_un_seul_diablotin():
    roles = distribuer_roles(IDS, random.Random(2))
    assert sum(1 for r in roles.values() if r.nom == "Diablotin") == 1


def test_meme_graine_meme_distribution():
    assert distribuer_roles(IDS, random.Random(3)) == distribuer_roles(IDS, random.Random(3))


def test_distribution_varie_avec_la_graine():
    resultats = {
        tuple(sorted((k, v.nom) for k, v in distribuer_roles(IDS, random.Random(g)).items()))
        for g in range(20)
    }
    assert len(resultats) > 1


def test_mauvais_nombre_de_joueurs_refuse():
    with pytest.raises(ValueError):
        distribuer_roles(IDS[:5], random.Random(1))


def test_identifiants_en_double_refuses():
    with pytest.raises(ValueError):
        distribuer_roles(["j1", "j1", "j2", "j3", "j4", "j5"], random.Random(1))


@pytest.mark.parametrize("graine", range(30))
def test_fausse_piste_jamais_le_demon_ni_la_voyante(graine):
    roles = distribuer_roles(IDS, random.Random(graine))
    piste = choisir_fausse_piste(roles, random.Random(graine))
    assert piste in roles
    assert roles[piste].nom not in ("Diablotin", "Voyante")


@pytest.mark.parametrize("graine", range(30))
def test_fausse_piste_est_un_joueur_du_bien(graine):
    roles = distribuer_roles(IDS, random.Random(graine))
    piste = choisir_fausse_piste(roles, random.Random(graine))
    assert roles[piste].alignement == Alignement.BON