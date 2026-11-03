import pytest
from pydantic import ValidationError

from backend.models import Effet, EtatJeu, Evenement, Joueur, Phase, Salon, TypeEffet
from backend.rules_engine import obtenir_role


def joueur(id: str, vivant: bool = True) -> Joueur:
    j = Joueur(id=id, nom=id.capitalize(), role=obtenir_role("Moine"))
    return j if vivant else j.mourir()


def protection_nuit_2() -> Effet:
    return Effet(
        type=TypeEffet.PROTEGE,
        source="Moine",
        tour_debut=2,
        phase_debut=Phase.NUIT,
        tour_fin=2,
        phase_fin=Phase.DISCUSSION,
    )


def etat() -> EtatJeu:
    return EtatJeu(
        joueurs=(joueur("odette"), joueur("brutus"), joueur("gaspard", vivant=False)),
        salons=(Salon(id="village", nom="Place du village", public=True, membres=("odette", "brutus")),),
    )


def test_etat_initial_nuit_tour_1():
    e = EtatJeu()
    assert e.tour == 1 and e.phase == Phase.NUIT and e.joueurs == () and e.journal == ()


def test_nuit_passe_a_la_discussion_dans_le_meme_tour():
    e = EtatJeu().passer_phase()
    assert e.tour == 1 and e.phase == Phase.DISCUSSION


def test_discussion_passe_au_vote_dans_le_meme_tour():
    e = EtatJeu(phase=Phase.DISCUSSION).passer_phase()
    assert e.tour == 1 and e.phase == Phase.VOTE


def test_vote_passe_a_la_nuit_au_tour_suivant():
    e = EtatJeu(phase=Phase.VOTE).passer_phase()
    assert e.tour == 2 and e.phase == Phase.NUIT


def test_passage_retire_les_effets_expires():
    e = EtatJeu(tour=2, phase=Phase.NUIT, joueurs=(joueur("odette").ajouter_effet(protection_nuit_2()),))
    e = e.passer_phase()
    assert not e.joueur("odette").a_effet(TypeEffet.PROTEGE)


def test_joueur_inconnu_leve_keyerror():
    with pytest.raises(KeyError):
        etat().joueur("inconnu")


def test_salon_inconnu_leve_keyerror():
    with pytest.raises(KeyError):
        etat().salon("inconnu")


def test_identifiants_joueurs_en_double_refuses():
    with pytest.raises(ValidationError):
        EtatJeu(joueurs=(joueur("odette"), joueur("odette")))


def test_remplacer_joueur_ne_touche_que_lui():
    e = etat()
    mort = e.joueur("odette").mourir()
    nouveau = e.remplacer_joueur(mort)
    assert not nouveau.joueur("odette").vivant
    assert nouveau.joueur("brutus") == e.joueur("brutus")
    assert e.joueur("odette").vivant


def test_joueurs_vivants_exclut_les_morts():
    ids = [j.id for j in etat().joueurs_vivants()]
    assert ids == ["odette", "brutus"]


def test_ajouter_evenement():
    e = etat().ajouter_evenement(Evenement(type="mort", tour=1, phase=Phase.NUIT))
    assert len(e.journal) == 1


def test_journal_public_visible_par_tous():
    e = etat().ajouter_evenement(Evenement(type="vote", tour=1, phase=Phase.DISCUSSION))
    assert len(e.journal_visible_par("gaspard")) == 1


def test_journal_prive_visible_seulement_des_destinataires():
    ev = Evenement(type="sonde", tour=1, phase=Phase.NUIT, public=False, destinataires=("odette",))
    e = etat().ajouter_evenement(ev)
    assert len(e.journal_visible_par("odette")) == 1
    assert e.journal_visible_par("brutus") == ()


def test_journal_moteur_seul_invisible_des_joueurs():
    ev = Evenement(type="interne", tour=1, phase=Phase.NUIT, public=False)
    e = etat().ajouter_evenement(ev)
    assert e.journal_visible_par("odette") == ()


def test_remplacer_salon():
    e = etat()
    salon = e.salon("village").fermer()
    assert not e.remplacer_salon(salon).salon("village").ouvert


def test_tour_zero_refuse():
    with pytest.raises(ValidationError):
        EtatJeu(tour=0)


def test_etat_immutable():
    with pytest.raises(ValidationError):
        etat().tour = 5


def test_str_resume_la_partie():
    texte = str(etat().passer_phase())
    assert texte.startswith("Tour 1, discussion")
    assert "Vivants (2) : Odette (Moine), Brutus (Moine)" in texte
    assert "Morts : Gaspard" in texte


def test_str_affiche_les_effets():
    e = EtatJeu(joueurs=(joueur("odette").ajouter_effet(protection_nuit_2()),))
    assert "[protege]" in str(e)