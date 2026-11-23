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


def verify_account(pseudo: str) -> None:
    """Marque l'adresse du compte comme vérifiée, comme si le joueur avait ouvert le lien reçu par e-mail
    (pour les tests qui ne portent pas sur la vérification elle-même)."""
    from backend.accounts import service
    from backend.db import get_session
    from backend.db.models import utcnow
    with get_session() as db:
        service.find_by_pseudo(db, pseudo).email_verified_at = utcnow()
        db.commit()
