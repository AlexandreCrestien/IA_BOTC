"""Opérations sur les comptes : inscription, connexion, modification, réinitialisation, suppression,
comptes inactifs, compte admin."""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.accounts.passwords import hash_password, password_error, spend_verification_time, verify_password
from backend.accounts.pseudo import INVALID_PSEUDO, normalize_pseudo, pseudo_is_valid
from backend.accounts.tokens import read_token
from backend.db import GameRecord, UnlockedAchievement, User, pseudo_key
from backend.db.models import utcnow

logger = logging.getLogger(__name__)

# Compte supprimé automatiquement sans connexion pendant cette durée (minimisation des données, RGPD)
INACTIVITY_LIMIT = timedelta(days=365)
# Dernière activité enregistrée au plus une fois par jour (évite une écriture à chaque requête)
ACTIVITY_PRECISION = timedelta(days=1)

PSEUDO_TAKEN = "Ce pseudo est déjà pris."
WRONG_PASSWORD = "Mot de passe actuel incorrect."


class AccountError(Exception):
    """Refus d'une opération, avec le message à afficher et le code HTTP."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def find_by_pseudo(db: Session, pseudo: str) -> Optional[User]:
    return db.scalar(select(User).where(User.pseudo_key == pseudo_key(normalize_pseudo(pseudo))))


def _check_pseudo(db: Session, pseudo: str, current: Optional[User] = None) -> str:
    pseudo = normalize_pseudo(pseudo)
    if not pseudo_is_valid(pseudo):
        raise AccountError(INVALID_PSEUDO)
    owner = find_by_pseudo(db, pseudo)
    if owner is not None and owner is not current:
        raise AccountError(PSEUDO_TAKEN, 409)
    return pseudo


def _check_password(password: str) -> None:
    error = password_error(password)
    if error:
        raise AccountError(error)


def _commit(db: Session) -> None:
    """Enregistre ; un pseudo pris entre la vérification et l'écriture donne le même refus."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AccountError(PSEUDO_TAKEN, 409)


def register(db: Session, pseudo: str, password: str) -> User:
    pseudo = _check_pseudo(db, pseudo)
    _check_password(password)
    now = utcnow()
    user = User(pseudo=pseudo, password_hash=hash_password(password), created_at=now, last_seen_at=now)
    db.add(user)
    _commit(db)
    logger.info("Compte créé : %s", pseudo)
    return user


def authenticate(db: Session, pseudo: str, password: str) -> Optional[User]:
    """Le compte si le pseudo et le mot de passe correspondent, sinon None (sans dire lequel est faux)."""
    user = find_by_pseudo(db, pseudo)
    if user is None:
        spend_verification_time(password)
        return None
    if not verify_password(password, user.password_hash):
        return None
    mark_active(db, user, force=True)
    return user


def _as_utc(moment: datetime) -> datetime:
    """SQLite rend les dates sans fuseau : elles sont toujours enregistrées en UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def mark_active(db: Session, user: User, force: bool = False) -> None:
    """Note l'activité du compte (connexion, visite connectée), au plus une fois par jour sauf force."""
    now = utcnow()
    if force or user.last_seen_at is None or now - _as_utc(user.last_seen_at) >= ACTIVITY_PRECISION:
        user.last_seen_at = now
        db.commit()


def user_from_token(db: Session, token: str) -> Optional[User]:
    """Compte du jeton, s'il est valide et n'a pas été invalidé depuis (token_version)."""
    claims = read_token(token)
    if claims is None:
        return None
    user = db.get(User, claims.user_id)
    if user is None or user.token_version != claims.version:
        return None
    mark_active(db, user)
    return user


def _require_current_password(user: User, current_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AccountError(WRONG_PASSWORD, 403)


def change_pseudo(db: Session, user: User, current_password: str, new_pseudo: str) -> User:
    _require_current_password(user, current_password)
    user.pseudo = _check_pseudo(db, new_pseudo, current=user)
    _commit(db)
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> User:
    """Les jetons déjà émis (autres appareils) ne sont plus valables ; l'appelant en délivre un nouveau."""
    _require_current_password(user, current_password)
    _check_password(new_password)
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    _commit(db)
    return user


def reset_password(db: Session, user: User) -> str:
    """Dépannage par l'admin : nouveau mot de passe temporaire, renvoyé une seule fois, et déconnexion du compte."""
    if user.is_admin:
        raise AccountError("Le mot de passe de l'administrateur se change depuis son profil.")
    temporary = secrets.token_urlsafe(9)  # 12 caractères
    user.password_hash = hash_password(temporary)
    user.token_version += 1
    _commit(db)
    logger.info("Mot de passe réinitialisé par l'admin pour %s", user.pseudo)
    return temporary


def delete_account(db: Session, user: User, reason: str = "à sa demande") -> None:
    """Suppression d'un compte, la même par le joueur, par l'admin ou pour inactivité :
    - supprimés : le compte (pseudo, mot de passe) et ses succès ;
    - gardées, anonymisées : ses parties, détachées du compte et datées au jour près (sans l'heure), pour les
      statistiques du jeu. Elles ne permettent plus de retrouver le joueur.
    Le compte admin ne peut pas être supprimé. L'appelant arrête d'abord la partie en cours du compte."""
    if user.is_admin:
        raise AccountError("Le compte administrateur ne peut pas être supprimé.")
    pseudo = user.pseudo
    db.execute(delete(UnlockedAchievement).where(UnlockedAchievement.user_id == user.id))
    for game in db.scalars(select(GameRecord).where(GameRecord.user_id == user.id)):
        game.user_id = None
        game.started_at = _as_utc(game.started_at).replace(hour=0, minute=0, second=0, microsecond=0)
        game.ended_at = None
    db.flush()
    db.delete(user)
    db.commit()
    logger.info("Compte supprimé (%s) : %s", reason, pseudo)


def inactive_accounts(db: Session, now: Optional[datetime] = None) -> list[User]:
    """Comptes joueurs sans activité depuis INACTIVITY_LIMIT (jamais le compte admin)."""
    limit = (now or utcnow()) - INACTIVITY_LIMIT
    return list(db.scalars(select(User).where(User.is_admin.is_(False), User.last_seen_at < limit)))


def delete_inactive_accounts(db: Session, keep: Iterable[int] = (), now: Optional[datetime] = None) -> list[str]:
    """Supprime les comptes inactifs depuis un an, sauf ceux de `keep` (partie en cours).
    Renvoie les pseudos supprimés."""
    keep = set(keep)
    deleted = []
    for user in inactive_accounts(db, now):
        if user.id in keep:
            continue
        deleted.append(user.pseudo)
        delete_account(db, user, reason="inactif depuis un an")
    return deleted


def ensure_admin(db: Session, pseudo: Optional[str] = None, password: Optional[str] = None) -> Optional[User]:
    """Crée le compte admin au démarrage (ADMIN_PSEUDO et ADMIN_PASSWORD du .env) s'il n'existe pas.
    S'il existe déjà, son mot de passe n'est pas modifié. Variables absentes ou invalides : pas d'admin."""
    pseudo = pseudo if pseudo is not None else os.getenv("ADMIN_PSEUDO", "")
    password = password if password is not None else os.getenv("ADMIN_PASSWORD", "")
    if not pseudo or not password:
        logger.warning("ADMIN_PSEUDO / ADMIN_PASSWORD absents du .env : aucun compte admin, panneau inaccessible.")
        return None

    existing = find_by_pseudo(db, pseudo)
    if existing is not None:
        if not existing.is_admin:
            logger.error("ADMIN_PSEUDO %r est déjà le pseudo d'un joueur : compte admin non créé.", pseudo)
            return None
        return existing
    try:
        user = register(db, pseudo, password)
    except AccountError as error:
        logger.error("Compte admin non créé : %s", error.message)
        return None
    user.is_admin = True
    db.commit()
    logger.info("Compte admin créé : %s", user.pseudo)
    return user
