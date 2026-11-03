import pytest
from pydantic import ValidationError

from backend.models import Alignement, Equipe, Phase, Role, TypeEffet
from backend.rules_engine import ROLES, obtenir_role


def moine() -> Role:
    return obtenir_role("Moine")


def test_moine_est_dans_le_catalogue():
    assert ROLES["Moine"] == moine()


def test_role_inconnu_refuse():
    with pytest.raises(KeyError):
        obtenir_role("Inexistant")


def diablotin() -> Role:
    return Role(nom="Diablotin", camp=Equipe.DEMON, phase=Phase.NUIT, effets=(TypeEffet.EMPOISONNE,))


def test_moine_est_du_bien():
    assert moine().alignement == Alignement.BON


def test_outsider_est_du_bien():
    recluse = Role(nom="Recluse", camp=Equipe.OUTSIDER)
    assert recluse.alignement == Alignement.BON


@pytest.mark.parametrize("camp", [Equipe.SBIRE, Equipe.DEMON])
def test_sbire_et_demon_sont_mauvais(camp):
    assert Role(nom="Test", camp=camp).alignement == Alignement.MAUVAIS


def test_role_sans_phase_precise():
    assert Role(nom="Recluse", camp=Equipe.OUTSIDER).phase is None


def test_effets_par_defaut_vides():
    assert Role(nom="Recluse", camp=Equipe.OUTSIDER).effets == ()


def test_nom_vide_refuse():
    with pytest.raises(ValidationError):
        Role(nom="", camp=Equipe.VILLAGEOIS)


def test_role_immutable():
    role = moine()
    with pytest.raises(ValidationError):
        role.nom = "autre"