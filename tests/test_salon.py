import pytest
from pydantic import ValidationError

from backend.models import Message, Phase, Salon


def salon_prive() -> Salon:
    return Salon(id="s1", nom="Odette et Silas", membres=("odette", "silas"))


def message(auteur: str = "odette", texte: str = "Attendons.") -> Message:
    return Message(auteur_id=auteur, texte=texte, tour=2, phase=Phase.DISCUSSION)


def test_salon_neuf_ouvert_sans_message():
    s = salon_prive()
    assert s.ouvert and s.messages == ()


def test_membre_peut_ecrire():
    s = salon_prive().ajouter_message(message("odette"))
    assert len(s.messages) == 1


def test_non_membre_ne_peut_pas_ecrire():
    with pytest.raises(ValueError):
        salon_prive().ajouter_message(message("brutus"))


def test_membre_voit_l_historique():
    s = salon_prive().ajouter_message(message("odette"))
    assert s.messages_visibles_par("silas") == s.messages


def test_non_membre_ne_voit_rien():
    s = salon_prive().ajouter_message(message("odette"))
    assert s.messages_visibles_par("brutus") == ()


def test_fermer_garde_l_historique_en_lecture():
    s = salon_prive().ajouter_message(message("odette")).fermer()
    assert not s.ouvert and len(s.messages) == 1 and s.messages_visibles_par("odette") == s.messages


def test_salon_ferme_refuse_les_messages():
    s = salon_prive().fermer()
    with pytest.raises(ValueError):
        s.ajouter_message(message("odette"))


def test_fermer_deux_fois_refuse():
    with pytest.raises(ValueError):
        salon_prive().fermer().fermer()


def test_ajouter_membre_puis_il_peut_ecrire():
    s = salon_prive().ajouter_membre("brutus")
    assert s.ajouter_message(message("brutus")).messages[0].auteur_id == "brutus"


def test_ajouter_membre_deja_present_refuse():
    with pytest.raises(ValueError):
        salon_prive().ajouter_membre("odette")


def test_salon_sans_membre_refuse():
    with pytest.raises(ValidationError):
        Salon(id="s1", nom="Vide", membres=())


def test_message_vide_refuse():
    with pytest.raises(ValidationError):
        message(texte="")


def test_salon_immutable():
    with pytest.raises(ValidationError):
        salon_prive().nom = "autre"