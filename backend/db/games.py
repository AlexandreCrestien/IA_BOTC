"""Opérations sur les parties enregistrées."""
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.models import GameRecord, GameStatus, utcnow


def interrupt_unfinished_games(db: Session) -> int:
    """Parties restées « en cours » au démarrage du serveur : il s'est arrêté pendant la partie,
    qui ne peut plus être reprise. Elles passent à « interrompue » (hors statistiques).
    Renvoie le nombre de parties concernées."""
    result = db.execute(
        update(GameRecord)
        .where(GameRecord.status == GameStatus.IN_PROGRESS)
        .values(status=GameStatus.INTERRUPTED, ended_at=utcnow())
    )
    return result.rowcount
