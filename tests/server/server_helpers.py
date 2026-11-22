"""Aides pour les tests du serveur (importées par les tests, pas des fixtures)."""
from backend.engine.human_port import QueueHumanPort
from backend.server.session import GameSession, set_current_session


def waiting_session(human_id: str = "h", kind: str | None = None, state=None, **request) -> GameSession:
    """Session courante dont le moteur attend une réponse de type `kind` (sans partie qui tourne).
    request : contenu de la demande (targets, count, choices, agent…)."""
    session = GameSession(human_id=human_id, port=QueueHumanPort(), state=state)
    if kind is not None:
        session.pending = {"kind": kind, "state": state, **request}
    set_current_session(session)
    return session
