"""Opérations sur les comptes : inscription, connexion, modification, mot de passe oublié, réinitialisation,
suppression, comptes inactifs, compte admin."""
import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, NamedTuple, Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.accounts.passwords import hash_password, password_error, spend_verification_time, verify_password
from backend.accounts.pseudo import INVALID_PSEUDO, normalize_pseudo, pseudo_is_valid
from backend.accounts.tokens import read_token
from backend.db import (
    AccountEvent,
    EmailVerificationToken,
    GameDetail,
    GameRecord,
    PasswordResetToken,
    UnlockedAchievement,
    User,
    pseudo_key,
)
from backend.db.models import utcnow

logger = logging.getLogger(__name__)

# Compte supprimé automatiquement sans connexion pendant cette durée (minimisation des données, RGPD)
INACTIVITY_LIMIT = timedelta(days=365)
# Avertissement par e-mail avant la suppression (le compte n'est supprimé qu'après ce délai)
INACTIVITY_WARNING = timedelta(days=30)
# Dernière activité enregistrée au plus une fois par jour (évite une écriture à chaque requête)
ACTIVITY_PRECISION = timedelta(days=1)
# Lien « mot de passe oublié » : durée de validité
RESET_TOKEN_LIFETIME = timedelta(minutes=30)
# Lien de vérification de l'adresse : durée de validité (un nouveau lien peut être demandé)
VERIFY_TOKEN_LIFETIME = timedelta(hours=24)
# Compte jamais vérifié : supprimé après ce délai (adresse peut-être saisie par erreur, pseudo et adresse libérés)
UNVERIFIED_ACCOUNT_LIFETIME = timedelta(hours=72)
# Durées de conservation (RGPD) : détail des parties (panel admin) et registre des modifications des comptes
GAME_DETAIL_LIFETIME = timedelta(days=183)   # 6 mois
ACCOUNT_EVENT_LIFETIME = timedelta(days=365)  # 1 an

# Registre des modifications : type d'événement -> libellé affiché dans le panel admin
ACCOUNT_EVENTS = {
    "account_created": "Compte créé",
    "email_verified": "Adresse e-mail confirmée",
    "email_corrected": "Adresse e-mail corrigée (avant confirmation)",
    "email_change_requested": "Changement d'adresse e-mail demandé",
    "email_changed": "Adresse e-mail remplacée",
    "pseudo_changed": "Pseudo modifié",
    "password_changed": "Mot de passe modifié (profil)",
    "password_reset_link": "Mot de passe réinitialisé (lien par e-mail)",
    "password_reset_admin": "Mot de passe réinitialisé par l'admin",
}

PSEUDO_TAKEN = "Ce pseudo est déjà pris."
EMAIL_TAKEN = "Cette adresse e-mail est déjà utilisée par un autre compte."
ALREADY_USED = "Ce pseudo ou cette adresse e-mail est déjà utilisé."
INVALID_EMAIL = "Adresse e-mail invalide."
WRONG_PASSWORD = "Mot de passe actuel incorrect."
INVALID_RESET_LINK = "Ce lien n'est plus valable (déjà utilisé ou expiré). Demandez-en un nouveau."
INVALID_VERIFY_LINK = ("Ce lien de vérification n'est plus valable (déjà utilisé ou expiré). "
                       "Connectez-vous pour en recevoir un nouveau.")
SAME_EMAIL = "C'est déjà l'adresse de votre compte."
ALREADY_VERIFIED = "Votre adresse e-mail est déjà vérifiée."

# Vérification volontairement simple : quelque chose@domaine.extension, sans espace
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
EMAIL_MAX_LENGTH = 254


class AccountError(Exception):
    """Refus d'une opération, avec le message à afficher et le code HTTP."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def log_event(db: Session, user: User, kind: str) -> None:
    """Ajoute une ligne au registre des modifications du compte : le type et la date, jamais les valeurs."""
    assert kind in ACCOUNT_EVENTS, kind
    db.add(AccountEvent(user_id=user.id, kind=kind, created_at=utcnow()))
    db.commit()


def find_by_pseudo(db: Session, pseudo: str) -> Optional[User]:
    return db.scalar(select(User).where(User.pseudo_key == pseudo_key(normalize_pseudo(pseudo))))


def normalize_email(email: str) -> str:
    """Adresse sans espaces autour, en minuscules : « Zoe@Exemple.fr » et « zoe@exemple.fr » sont la même."""
    return email.strip().lower()


def find_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def find_by_login(db: Session, login: str) -> Optional[User]:
    """Compte désigné par son pseudo ou son adresse e-mail (un pseudo ne contient jamais « @ »)."""
    return find_by_email(db, login) if "@" in login else find_by_pseudo(db, login)


def _check_pseudo(db: Session, pseudo: str, current: Optional[User] = None) -> str:
    pseudo = normalize_pseudo(pseudo)
    if not pseudo_is_valid(pseudo):
        raise AccountError(INVALID_PSEUDO)
    owner = find_by_pseudo(db, pseudo)
    if owner is not None and owner is not current:
        raise AccountError(PSEUDO_TAKEN, 409)
    return pseudo


def _check_email(db: Session, email: str, current: Optional[User] = None) -> str:
    email = normalize_email(email)
    if len(email) > EMAIL_MAX_LENGTH or not EMAIL_PATTERN.fullmatch(email):
        raise AccountError(INVALID_EMAIL)
    owner = find_by_email(db, email)
    if owner is not None and owner is not current:
        raise AccountError(EMAIL_TAKEN, 409)
    return email


def _check_password(password: str) -> None:
    error = password_error(password)
    if error:
        raise AccountError(error)


def _commit(db: Session) -> None:
    """Enregistre ; un pseudo ou une adresse pris entre la vérification et l'écriture donne un refus."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AccountError(ALREADY_USED, 409)


def _create_user(db: Session, pseudo: str, password: str, email: Optional[str], verified: bool = False) -> User:
    pseudo = _check_pseudo(db, pseudo)
    email = _check_email(db, email) if email is not None else None
    _check_password(password)
    now = utcnow()
    user = User(pseudo=pseudo, email=email, password_hash=hash_password(password), created_at=now, last_seen_at=now,
                email_verified_at=now if verified and email else None)
    db.add(user)
    _commit(db)
    logger.info("Compte créé : %s", pseudo)
    return user


def register(db: Session, pseudo: str, password: str, email: str) -> User:
    """Inscription d'un joueur : pseudo, adresse e-mail (obligatoire) et mot de passe.
    L'adresse reste à vérifier : l'appelant envoie le lien (create_verification_token)."""
    if not email or not email.strip():
        raise AccountError("Veuillez indiquer une adresse e-mail.")
    user = _create_user(db, pseudo, password, email)
    log_event(db, user, "account_created")
    return user


def authenticate(db: Session, login: str, password: str) -> Optional[User]:
    """Le compte si l'identifiant (pseudo ou e-mail) et le mot de passe correspondent, sinon None
    (sans dire lequel est faux)."""
    user = find_by_login(db, login)
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
    """Note l'activité du compte (connexion, visite connectée), au plus une fois par jour sauf force.
    Un avertissement d'inactivité déjà envoyé n'a plus lieu d'être : il est effacé."""
    now = utcnow()
    if force or user.last_seen_at is None or now - _as_utc(user.last_seen_at) >= ACTIVITY_PRECISION:
        user.last_seen_at = now
        user.inactivity_warned_at = None
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
    log_event(db, user, "pseudo_changed")
    return user


def change_email(db: Session, user: User, current_password: str, new_email: str) -> str:
    """Nouvelle adresse, à confirmer par le lien que l'appelant y envoie. Renvoie le jeton du lien.
    - adresse déjà vérifiée : elle reste en place jusqu'à la confirmation de la nouvelle (le joueur ne perd
      jamais l'accès à son compte) ;
    - adresse pas encore vérifiée (faute de frappe à l'inscription) : remplacée tout de suite."""
    _require_current_password(user, current_password)
    email = _check_email(db, new_email, current=user)
    if email == user.email and user.email_verified:
        raise AccountError(SAME_EMAIL)
    if not user.email_verified:
        user.email = email
        _commit(db)
        log_event(db, user, "email_corrected")
    else:
        log_event(db, user, "email_change_requested")
    return create_verification_token(db, user, email)


def change_password(db: Session, user: User, current_password: str, new_password: str) -> User:
    """Les jetons déjà émis (autres appareils) ne sont plus valables ; l'appelant en délivre un nouveau."""
    _require_current_password(user, current_password)
    _check_password(new_password)
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    _commit(db)
    log_event(db, user, "password_changed")
    return user


def reset_password(db: Session, user: User) -> str:
    """Dépannage par l'admin : nouveau mot de passe temporaire, renvoyé une seule fois, et déconnexion du compte."""
    if user.is_admin:
        raise AccountError("Le mot de passe de l'administrateur se change depuis son profil.")
    temporary = secrets.token_urlsafe(9)  # 12 caractères
    user.password_hash = hash_password(temporary)
    user.token_version += 1
    _commit(db)
    log_event(db, user, "password_reset_admin")
    logger.info("Mot de passe réinitialisé par l'admin pour %s", user.pseudo)
    return temporary


# --- Mot de passe oublié -----------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_reset_token(db: Session, user: User) -> str:
    """Nouveau lien « mot de passe oublié » : renvoie le jeton à mettre dans le lien (seule son empreinte est
    stockée). Les liens précédents encore valables sont annulés : seul le dernier fonctionne."""
    now = utcnow()
    for previous in db.scalars(select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))):
        previous.used_at = now
    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(user_id=user.id, token_hash=_token_hash(token), created_at=now,
                              expires_at=now + RESET_TOKEN_LIFETIME))
    db.commit()
    return token


# --- Vérification de l'adresse ------------------------------------------------------------

def create_verification_token(db: Session, user: User, email: Optional[str] = None) -> str:
    """Nouveau lien de vérification pour `email` (par défaut l'adresse du compte). Les liens précédents
    encore valables sont annulés. Renvoie le jeton à mettre dans le lien (seule son empreinte est stockée)."""
    now = utcnow()
    for previous in db.scalars(select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))):
        previous.used_at = now
    token = secrets.token_urlsafe(32)
    db.add(EmailVerificationToken(user_id=user.id, email=email or user.email, token_hash=_token_hash(token),
                                  created_at=now, expires_at=now + VERIFY_TOKEN_LIFETIME))
    db.commit()
    return token


def verification_target(db: Session, user: User) -> Optional[str]:
    """Adresse à confirmer : nouvelle adresse en attente, sinon celle du compte si elle n'est pas vérifiée."""
    pending = pending_email(db, user)
    if pending:
        return pending
    return user.email if user.email and not user.email_verified else None


def pending_email(db: Session, user: User) -> Optional[str]:
    """Nouvelle adresse demandée et pas encore confirmée (lien encore valable), ou None."""
    entry = db.scalar(select(EmailVerificationToken)
                      .where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))
                      .order_by(EmailVerificationToken.id.desc()))
    if entry is None or _as_utc(entry.expires_at) < utcnow() or entry.email == user.email:
        return None
    return entry.email


class EmailVerified(NamedTuple):
    user: User
    previous_email: Optional[str]  # ancienne adresse vérifiée remplacée (à prévenir), ou None


def verify_email(db: Session, token: str) -> EmailVerified:
    """Lien de vérification ouvert : l'adresse est confirmée (et remplace l'ancienne si c'était un changement).
    Renvoie aussi l'ancienne adresse vérifiée qu'elle remplace, pour la prévenir."""
    entry = db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == _token_hash(token)))
    if entry is None or entry.used_at is not None or _as_utc(entry.expires_at) < utcnow():
        raise AccountError(INVALID_VERIFY_LINK)
    user = db.get(User, entry.user_id)
    owner = find_by_email(db, entry.email)
    if owner is not None and owner is not user:  # prise par un autre compte entre-temps
        raise AccountError(EMAIL_TAKEN, 409)
    previous = user.email if user.email_verified and user.email != entry.email else None
    now = utcnow()
    user.email = entry.email
    user.email_verified_at = now
    entry.used_at = now
    _commit(db)
    log_event(db, user, "email_changed" if previous else "email_verified")
    logger.info("Adresse e-mail vérifiée pour %s", user.pseudo)
    return EmailVerified(user, previous)


def unverified_accounts_to_delete(db: Session, now: Optional[datetime] = None) -> list[User]:
    """Comptes joueurs jamais vérifiés, créés depuis plus de UNVERIFIED_ACCOUNT_LIFETIME."""
    limit = (now or utcnow()) - UNVERIFIED_ACCOUNT_LIFETIME
    return list(db.scalars(select(User).where(
        User.is_admin.is_(False), User.email_verified_at.is_(None), User.created_at < limit)))


def delete_unverified_accounts(db: Session, keep: Iterable[int] = (), now: Optional[datetime] = None) -> list[str]:
    """Supprime les comptes jamais vérifiés après 72 heures (sauf `keep` : partie en cours). Renvoie les pseudos."""
    keep = set(keep)
    deleted = []
    for user in unverified_accounts_to_delete(db, now):
        if user.id in keep:
            continue
        deleted.append(user.pseudo)
        delete_account(db, user, reason="adresse jamais vérifiée")
    return deleted


def delete_expired_records(db: Session, now: Optional[datetime] = None) -> int:
    """Durées de conservation : efface le détail des parties de plus de 6 mois et le registre des
    modifications de plus d'un an. Renvoie le nombre de lignes effacées."""
    now = now or utcnow()
    count = db.execute(delete(GameDetail).where(GameDetail.created_at < now - GAME_DETAIL_LIFETIME)).rowcount
    count += db.execute(delete(AccountEvent).where(AccountEvent.created_at < now - ACCOUNT_EVENT_LIFETIME)).rowcount
    db.commit()
    return count


def delete_stale_reset_tokens(db: Session, now: Optional[datetime] = None) -> int:
    """Efface les liens « mot de passe oublié » et de vérification expirés depuis plus d'un jour (utilisés ou non) :
    ils ne servent plus et garderaient l'historique des demandes. Renvoie le nombre effacé."""
    limit = (now or utcnow()) - timedelta(days=1)
    count = 0
    for table in (PasswordResetToken, EmailVerificationToken):
        count += db.execute(delete(table).where(table.expires_at < limit)).rowcount
    db.commit()
    return count


def reset_password_with_token(db: Session, token: str, new_password: str) -> User:
    """Nouveau mot de passe choisi depuis le lien : lien à usage unique, déconnexion de tous les appareils."""
    entry = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _token_hash(token)))
    if entry is None or entry.used_at is not None or _as_utc(entry.expires_at) < utcnow():
        raise AccountError(INVALID_RESET_LINK)
    _check_password(new_password)
    user = db.get(User, entry.user_id)
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    entry.used_at = utcnow()
    mark_active(db, user, force=True)
    log_event(db, user, "password_reset_link")
    logger.info("Mot de passe réinitialisé par lien pour %s", user.pseudo)
    return user


def delete_account(db: Session, user: User, reason: str = "à sa demande") -> None:
    """Suppression d'un compte, la même par le joueur, par l'admin ou pour inactivité :
    - supprimés : le compte (pseudo, adresse e-mail, mot de passe), ses succès, ses liens envoyés par e-mail,
      le registre de ses modifications et le détail de ses parties (chat, mémoire des IA) ;
    - gardées, anonymisées : ses parties, détachées du compte et datées au jour près (sans l'heure), pour les
      statistiques du jeu. Elles ne permettent plus de retrouver le joueur.
    Le compte admin ne peut pas être supprimé. L'appelant arrête d'abord la partie en cours du compte."""
    if user.is_admin:
        raise AccountError("Le compte administrateur ne peut pas être supprimé.")
    pseudo = user.pseudo
    db.execute(delete(UnlockedAchievement).where(UnlockedAchievement.user_id == user.id))
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
    db.execute(delete(AccountEvent).where(AccountEvent.user_id == user.id))
    game_ids = select(GameRecord.id).where(GameRecord.user_id == user.id)
    db.execute(delete(GameDetail).where(GameDetail.game_id.in_(game_ids)))
    for game in db.scalars(select(GameRecord).where(GameRecord.user_id == user.id)):
        game.user_id = None
        game.started_at = _as_utc(game.started_at).replace(hour=0, minute=0, second=0, microsecond=0)
        game.ended_at = None
    db.flush()
    db.delete(user)
    db.commit()
    logger.info("Compte supprimé (%s) : %s", reason, pseudo)


def accounts_to_warn(db: Session, now: Optional[datetime] = None) -> list[User]:
    """Comptes joueurs inactifs depuis INACTIVITY_LIMIT - INACTIVITY_WARNING, avec une adresse vérifiée (on n'écrit
    jamais à une adresse non vérifiée), pas encore prévenus."""
    limit = (now or utcnow()) - (INACTIVITY_LIMIT - INACTIVITY_WARNING)
    return list(db.scalars(select(User).where(
        User.is_admin.is_(False), User.last_seen_at < limit, User.email_verified_at.is_not(None),
        User.inactivity_warned_at.is_(None))))


def mark_warned(db: Session, user: User, now: Optional[datetime] = None) -> None:
    user.inactivity_warned_at = now or utcnow()
    db.commit()


def deletion_date(user: User) -> datetime:
    """Date à partir de laquelle le compte inactif sera supprimé."""
    return _as_utc(user.last_seen_at) + INACTIVITY_LIMIT


def inactive_accounts(db: Session, now: Optional[datetime] = None) -> list[User]:
    """Comptes joueurs à supprimer : sans activité depuis INACTIVITY_LIMIT (jamais le compte admin), et prévenus
    depuis au moins INACTIVITY_WARNING. Un compte sans adresse vérifiée ne peut pas être prévenu : il est supprimé à
    l'échéance."""
    now = now or utcnow()
    limit = now - INACTIVITY_LIMIT
    warned_long_enough = User.inactivity_warned_at <= now - INACTIVITY_WARNING
    return list(db.scalars(select(User).where(
        User.is_admin.is_(False), User.last_seen_at < limit,
        User.email_verified_at.is_(None) | warned_long_enough)))


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


def ensure_admin(db: Session, pseudo: Optional[str] = None, password: Optional[str] = None,
                 email: Optional[str] = None) -> Optional[User]:
    """Crée le compte admin au démarrage (ADMIN_PSEUDO, ADMIN_PASSWORD et, facultatif, ADMIN_EMAIL du .env)
    s'il n'existe pas. S'il existe déjà, son mot de passe n'est pas modifié ; son adresse est ajoutée si elle
    manquait. Variables absentes ou invalides : pas d'admin."""
    pseudo = pseudo if pseudo is not None else os.getenv("ADMIN_PSEUDO", "")
    password = password if password is not None else os.getenv("ADMIN_PASSWORD", "")
    email = email if email is not None else os.getenv("ADMIN_EMAIL", "")
    if not pseudo or not password:
        logger.warning("ADMIN_PSEUDO / ADMIN_PASSWORD absents du .env : aucun compte admin, panneau inaccessible.")
        return None

    existing = find_by_pseudo(db, pseudo)
    if existing is not None:
        if not existing.is_admin:
            logger.error("ADMIN_PSEUDO %r est déjà le pseudo d'un joueur : compte admin non créé.", pseudo)
            return None
        if email and existing.email is None:
            try:
                existing.email = _check_email(db, email, current=existing)
                existing.email_verified_at = utcnow()
                _commit(db)
            except AccountError as error:
                logger.error("ADMIN_EMAIL non enregistré : %s", error.message)
        return existing
    try:
        user = _create_user(db, pseudo, password, email or None, verified=True)  # adresse du .env : de confiance
    except AccountError as error:
        logger.error("Compte admin non créé : %s", error.message)
        return None
    user.is_admin = True
    db.commit()
    logger.info("Compte admin créé : %s", user.pseudo)
    return user
