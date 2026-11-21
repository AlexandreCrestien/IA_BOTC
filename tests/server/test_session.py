"""Session de la partie en cours : une réponse n'est transmise au moteur que pour la demande attendue."""
from backend.engine.human_port import QueueHumanPort
from backend.server.session import GameSession


def session_waiting_for(kind):
    session = GameSession(human_id="h", port=QueueHumanPort())
    session.pending = {"kind": kind, "state": None}
    return session


def test_answer_accepted_for_the_expected_request():
    session = session_waiting_for("vote")
    assert session.answer("vote", None) is True
    assert session.port.answers.get_nowait() is None
    assert session.pending is None


def test_answer_refused_for_another_request():
    session = session_waiting_for("night_choice")
    assert session.answer("vote", "imp") is False
    assert session.port.answers.empty()
    assert session.waits_for("night_choice")


def test_answer_refused_without_pending_request():
    session = GameSession(human_id="h")
    assert session.answer("vote", "imp") is False


def test_one_answer_per_request():
    session = session_waiting_for("public_message")
    assert session.answer("public_message", "bonjour") is True
    assert session.answer("public_message", "encore") is False
    assert session.port.answers.get_nowait() == "bonjour"
    assert session.port.answers.empty()


def test_running_depends_on_the_game_task():
    session = GameSession(human_id="h")
    assert not session.running  # mise en place pas encore lancée
