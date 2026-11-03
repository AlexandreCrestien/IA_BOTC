import pytest
from pydantic import ValidationError

from backend.models import Effet, Equipe, Joueur, Phase, Role, TypeEffet
from backend.rules_engine import obtenir_role


def joueur(**kwargs) -> Joueur:
    base = dict(id="j1", nom="Odette", role=obtenir_role("Moine"))
    base.update(kwargs)
    return Joueur(**base)


def protection() -> Effet:
    return Effet(
        type=TypeEffet.PROTEGE,
        source="Moine",
        tour_debut=2,
        phase_debut=Phase.NUIT,
        tour_fin=2,
        phase_fin=Phase.DISCUSSION,
    )


def test_joueur_vivant_par_defaut():
    j = joueur()
    assert j.vivant and not j.vote_fantome and j.effets == ()


def test_moine_peut_agir_quand_vivant():
    assert joueur().peut_agir


def test_mort_ne_peut_plus_agir():
    assert not joueur().mourir().peut_agir


def test_role_sans_phase_ne_peut_pas_agir():
    assert not joueur(role=Role(nom="Recluse", camp=Equipe.OUTSIDER)).peut_agir


def test_pouvoir_deja_utilise_bloque_action():
    assert not joueur(pouvoir_utilise=True).peut_agir


def test_mort_garde_un_vote_fantome():
    j = joueur().mourir()
    assert not j.vivant and j.vote_fantome and j.peut_voter


def test_vote_fantome_utilise_une_seule_fois():
    j = joueur().mourir().utiliser_vote_fantome()
    assert not j.peut_voter


def test_mourir_deux_fois_refuse():
    with pytest.raises(ValueError):
        joueur().mourir().mourir()


def test_vote_fantome_refuse_si_vivant():
    with pytest.raises(ValueError):
        joueur().utiliser_vote_fantome()


def test_ajouter_effet_sans_modifier_l_original():
    original = joueur()
    nouveau = original.ajouter_effet(protection())
    assert original.effets == () and nouveau.a_effet(TypeEffet.PROTEGE)


def test_retirer_effets_expires_garde_les_actifs():
    actif = Effet(type=TypeEffet.EMPOISONNE, source="Test", tour_debut=1, phase_debut=Phase.NUIT)
    j = joueur().ajouter_effet(protection()).ajouter_effet(actif)
    j = j.retirer_effets_expires(2, Phase.DISCUSSION)
    assert not j.a_effet(TypeEffet.PROTEGE) and j.a_effet(TypeEffet.EMPOISONNE)


def test_joueur_immutable():
    with pytest.raises(ValidationError):
        joueur().nom = "autre"


def test_nom_vide_refuse():
    with pytest.raises(ValidationError):
        joueur(nom="")



def test_liens_vides_par_defaut():
    assert joueur().liens == {}


def test_avec_lien_ne_modifie_pas_l_original():
    original = joueur()
    nouveau = original.avec_lien("maitre", "odette")
    assert original.liens == {} and nouveau.lien("maitre") == "odette"