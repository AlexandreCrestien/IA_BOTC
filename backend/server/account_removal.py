"""Suppression d'un compte côté serveur : la même pour le joueur (tableau de bord), l'admin (panel)
et la purge des comptes inactifs (maintenance.py).

La partie en cours du compte est arrêtée d'abord (son écran de jeu revient à l'accueil), puis le compte est
supprimé : compte et succès effacés, parties gardées anonymement (backend/accounts/service.py, delete_account).
"""
import asyncio
import logging

from sqlalchemy.orm import Session

from backend.accounts import emails, service
from backend.mail import send_mail
from backend.db import User, get_session
from backend.server import game_runner
from backend.server.protocol import send
from backend.server.schemas import GameAbandoned
from backend.server.session import current_session

logger = logging.getLogger(__name__)

# Tâche de nettoyage : au démarrage, puis une fois par jour. Les échéances sont donc respectées à un jour près
# (un compte jamais vérifié est supprimé entre 72 et 96 heures après l'inscription).
PURGE_INTERVAL_SECONDS = 24 * 3600


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


def warn_inactive_accounts() -> list[str]:
    """Prévient par e-mail les comptes inactifs depuis 11 mois : sans connexion dans les 30 jours, ils seront
    supprimés. Un compte n'est marqué « prévenu » que si l'e-mail est bien parti. Renvoie les pseudos prévenus."""
    warned = []
    with get_session() as db:
        for user in service.accounts_to_warn(db):
            subject, text = emails.inactivity_warning(user.pseudo, service.deletion_date(user))
            if send_mail(user.email, subject, text):
                service.mark_warned(db, user)
                warned.append(user.pseudo)
    if warned:
        logger.info("%d compte(s) inactif(s) prévenu(s) avant suppression", len(warned))
    return warned


def purge_inactive_accounts() -> list[str]:
    """Tâche de nettoyage : prévient les comptes bientôt concernés, efface les liens envoyés par e-mail expirés,
    supprime les comptes jamais vérifiés après 72 heures, puis ceux inactifs depuis un an et prévenus depuis
    30 jours au moins (ou sans adresse vérifiée). Un compte dont la partie est en cours est épargné.
    Renvoie les pseudos supprimés."""
    warn_inactive_accounts()
    with get_session() as db:
        service.delete_stale_reset_tokens(db)
        service.delete_expired_records(db)  # détail des parties (6 mois), registre des modifications (1 an)
    session = current_session()
    keep = [session.user_id] if session is not None and session.running and session.user_id else []
    with get_session() as db:
        unverified = service.delete_unverified_accounts(db, keep=keep)
        deleted = service.delete_inactive_accounts(db, keep=keep)
    if unverified:
        logger.info("%d compte(s) jamais vérifié(s) supprimé(s) après 72 heures", len(unverified))
    deleted = unverified + deleted
    if deleted:
        logger.info("%d compte(s) inactif(s) depuis un an supprimé(s)", len(deleted))
    return deleted


async def purge_periodically() -> None:
    """Tâche de fond lancée au démarrage du serveur : nettoyage, puis une fois par jour."""
    while True:
        try:
            purge_inactive_accounts()
        except Exception:  # noqa: BLE001 : une erreur ne doit pas arrêter la tâche
            logger.exception("Échec de la purge des comptes inactifs")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)
