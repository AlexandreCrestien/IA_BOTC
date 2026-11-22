"""Suppression d'un compte côté serveur : la même pour le joueur (tableau de bord), l'admin (panel)
et la purge des comptes inactifs (maintenance.py).

La partie en cours du compte est arrêtée d'abord (son écran de jeu revient à l'accueil), puis le compte est
supprimé : compte et succès effacés, parties gardées anonymement (backend/accounts/service.py, delete_account).
"""
import asyncio
import logging

from sqlalchemy.orm import Session

from backend.accounts import service
from backend.db import User, get_session
from backend.server import game_runner
from backend.server.protocol import send
from backend.server.schemas import GameAbandoned
from backend.server.session import current_session

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 24 * 3600  # recherche des comptes inactifs : au démarrage, puis une fois par jour


async def stop_game_of(user_id: int) -> None:
    """Arrête la partie en cours de ce compte, s'il en a une (comptée comme abandonnée avant l'anonymisation)."""
    session = current_session()
    if session is not None and session.running and session.user_id == user_id:
        human_id = session.human_id
        game_runner.abandon_game(human_id)
        await send(human_id, GameAbandoned())


async def remove_account(db: Session, user: User, reason: str) -> None:
    """Arrête la partie en cours du compte puis le supprime. Lève AccountError pour le compte admin."""
    if user.is_admin:
        raise service.AccountError("Le compte administrateur ne peut pas être supprimé.")
    await stop_game_of(user.id)
    service.delete_account(db, user, reason=reason)


def purge_inactive_accounts() -> list[str]:
    """Supprime les comptes sans activité depuis un an. Un compte dont la partie est en cours est épargné :
    il est actif. Renvoie les pseudos supprimés."""
    session = current_session()
    keep = [session.user_id] if session is not None and session.running and session.user_id else []
    with get_session() as db:
        deleted = service.delete_inactive_accounts(db, keep=keep)
    if deleted:
        logger.info("%d compte(s) inactif(s) depuis un an supprimé(s)", len(deleted))
    return deleted


async def purge_periodically() -> None:
    """Tâche de fond lancée au démarrage du serveur : purge, puis une fois par jour."""
    while True:
        try:
            purge_inactive_accounts()
        except Exception:  # noqa: BLE001 : une erreur ne doit pas arrêter la tâche
            logger.exception("Échec de la purge des comptes inactifs")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)
