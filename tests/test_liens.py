import pytest

from backend.models import Joueur
from backend.rules_engine import definir_lien, obtenir_role


def joueur(id: str, role: str) -> Joueur:
    return Joueur(id=id, nom=id.capitalize(), role=obtenir_role(role))


def test_majordome_pose_un_maitre():
    m = definir_lien(joueur("m1", "Majordome"), "maitre", "odette")
    assert m.lien("maitre") == "odette"


def test_voyante_pose_une_fausse_piste():
    v = definir_lien(joueur("v1", "Voyante"), "fausse_piste", "odette")
    assert v.lien("fausse_piste") == "odette"


def test_cle_non_autorisee_refusee():
    with pytest.raises(ValueError):
        definir_lien(joueur("m1", "Majordome"), "fausse_piste", "odette")


def test_role_sans_lien_refuse_tout():
    with pytest.raises(ValueError):
        definir_lien(joueur("m1", "Moine"), "maitre", "odette")


def test_joueur_ne_peut_pas_se_designer():
    with pytest.raises(ValueError):
        definir_lien(joueur("m1", "Majordome"), "maitre", "m1")


def test_definir_lien_renvoie_un_nouvel_objet():
    original = joueur("m1", "Majordome")
    nouveau = definir_lien(original, "maitre", "odette")
    assert original.lien("maitre") is None and nouveau.lien("maitre") == "odette"