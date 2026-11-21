"""Session de la partie en cours : une réponse n'est transmise au moteur que pour la demande attendue."""
from backend.human_port import QueueHumanPort
from backend.server.session import GameSession


def session_waiting_for(kind):
    session = GameSession(human_id="h", port=QueueHumanPort())
    session.pending = {"kind": kind, "state": None}
    return session


def test_reponse_acceptee_pour_la_demande_attendue():
    session = session_waiting_for("vote")
    assert session.answer("vote", None) is True
    assert session.port.answers.get_nowait() is None
    assert session.pending is None


def test_reponse_refusee_pour_une_autre_demande():
    session = session_waiting_for("night_choice")
    assert session.answer("vote", "imp") is False
    assert session.port.answers.empty()
    assert session.waits_for("night_choice")


def test_reponse_refusee_sans_demande_en_attente():
    session = GameSession(human_id="h")
    assert session.answer("vote", "imp") is False


def test_une_seule_reponse_par_demande():
    session = session_waiting_for("public_message")
    assert session.answer("public_message", "bonjour") is True
    assert session.answer("public_message", "encore") is False
    assert session.port.answers.get_nowait() == "bonjour"
    assert session.port.answers.empty()


def test_partie_en_cours_selon_sa_tache():
    session = GameSession(human_id="h")
    assert not session.running  # mise en place pas encore lancée
