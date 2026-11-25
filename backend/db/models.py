"""Tables de la base : comptes, parties jouées, succès débloqués.

Les valeurs stockées sont en anglais (clés de rôle, camps, statuts) ; le front les traduit à l'affichage.
"""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates

from backend.models import Alignment, RoleKey


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    """Date au format ISO avec son fuseau, pour le front. Les dates sont toujours enregistrées en UTC ;
    SQLite les rend sans fuseau, PostgreSQL avec."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat()


def _enum(enum_class) -> SAEnum:
    """Colonne texte qui stocke la valeur de l'énumération ("reaper", "good"…), pas son nom."""
    return SAEnum(enum_class, native_enum=False, length=20, validate_strings=True,
                  values_callable=lambda members: [m.value for m in members])


class GameStatus(StrEnum):
    IN_PROGRESS = "in_progress"  # partie lancée, pas encore terminée
    WON = "won"
    LOST = "lost"
    ABANDONED = "abandoned"      # défaite (abandon)
    INTERRUPTED = "interrupted"  # serveur arrêté ou planté : hors statistiques


# Parties prises en compte dans les statistiques
COUNTED_STATUSES = (GameStatus.WON, GameStatus.LOST, GameStatus.ABANDONED)


class Base(DeclarativeBase):
    # Dates avec fuseau : TIMESTAMP WITH TIME ZONE sous PostgreSQL (sans effet sous SQLite).
    # Sans fuseau, PostgreSQL convertirait les dates selon le fuseau de la session.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class User(Base):
    __tablename__ = "users"
    # Contrainte nommée : une migration peut la retrouver pour la supprimer (retour arrière)
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pseudo: Mapped[str] = mapped_column(String(20))
    # Pseudo sans tenir compte de la casse (« Vesper » et « vesper » sont le même compte).
    # Rempli automatiquement à chaque affectation de pseudo.
    pseudo_key: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Incrémenté pour invalider les jetons déjà émis (changement de mot de passe, réinitialisation)
    token_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Dernière activité (connexion, visite connectée, au plus une mise à jour par jour) :
    # un compte inactif depuis un an est supprimé automatiquement (backend/server/account_removal.py)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Adresse e-mail, en minuscules : connexion, mot de passe oublié, avertissement avant suppression.
    # Obligatoire à l'inscription ; vide seulement pour le compte admin créé sans ADMIN_EMAIL.
    email: Mapped[Optional[str]] = mapped_column(String(254))
    # Avertissement « compte bientôt supprimé pour inactivité » envoyé (remis à vide à la reconnexion)
    inactivity_warned_at: Mapped[Optional[datetime]]
    # Adresse confirmée par le lien reçu par e-mail. Vide : compte en attente (pas de tableau de bord ni de
    # partie avec ce compte, aucun autre e-mail envoyé), supprimé s'il n'est pas vérifié sous 72 heures.
    email_verified_at: Mapped[Optional[datetime]]

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    games: Mapped[list["GameRecord"]] = relationship(back_populates="user")
    achievements: Mapped[list["UnlockedAchievement"]] = relationship(back_populates="user")

    @validates("pseudo")
    def _sync_pseudo_key(self, _key: str, pseudo: str) -> str:
        self.pseudo_key = pseudo_key(pseudo)
        return pseudo


def pseudo_key(pseudo: str) -> str:
    """Forme du pseudo utilisée pour l'unicité et la recherche."""
    return pseudo.casefold()


class GameRecord(Base):
    """Une partie jouée par un compte. Les parties des invités ne sont pas enregistrées, sauf s'ils s'inscrivent
    pendant la partie ou sur l'écran de fin : elle est alors enregistrée à ce moment-là, pour le nouveau compte.

    user_id vide : partie anonymisée, après la suppression de son compte. Elle ne garde que le résumé
    (jour, rôle, camp, issue, tours), sans lien avec personne, pour les statistiques du jeu."""
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[Optional[datetime]]
    role: Mapped[RoleKey] = mapped_column(_enum(RoleKey))
    alignment: Mapped[Alignment] = mapped_column(_enum(Alignment))
    turns: Mapped[int] = mapped_column(default=0)
    status: Mapped[GameStatus] = mapped_column(_enum(GameStatus), default=GameStatus.IN_PROGRESS, index=True)

    user: Mapped[Optional[User]] = relationship(back_populates="games")


class UnlockedAchievement(Base):
    """Succès débloqué par un compte (une seule fois par compte). code : identifiant défini dans le code."""
    __tablename__ = "unlocked_achievements"
    __table_args__ = (UniqueConstraint("user_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    unlocked_at: Mapped[datetime] = mapped_column(default=utcnow)
    game_id: Mapped[Optional[int]] = mapped_column(ForeignKey("games.id"))

    user: Mapped[User] = relationship(back_populates="achievements")


class PasswordResetToken(Base):
    """Lien « mot de passe oublié » : usage unique, valable RESET_TOKEN_LIFETIME (backend/accounts/service.py).
    Seule l'empreinte du jeton est stockée : qui lit la base ne peut pas s'en servir."""
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[Optional[datetime]]


class EmailVerificationToken(Base):
    """Lien de vérification d'adresse : à l'inscription, ou pour confirmer une nouvelle adresse (email : l'adresse
    à confirmer, qui ne remplace l'ancienne qu'une fois confirmée). Usage unique ; seule l'empreinte est stockée."""
    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[Optional[datetime]]


class GameDetail(Base):
    """Détail complet d'une partie d'un compte (chat, votes, nuits, mémoire des IA), enregistré à sa fin pour le
    panel admin (débogage, service client). Contient le pseudo et les messages libres du joueur : impossible à
    anonymiser, donc supprimé avec le compte, et au bout de GAME_DETAIL_LIFETIME (backend/accounts/service.py)."""
    __tablename__ = "game_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    data: Mapped[dict] = mapped_column(JSON)


class AccountEvent(Base):
    """Registre des modifications d'un compte (sécurité, service client) : le type d'événement et sa date,
    jamais les valeurs (ni ancienne adresse, ni mot de passe). Supprimé avec le compte, et au bout de
    ACCOUNT_EVENT_LIFETIME (backend/accounts/service.py)."""
    __tablename__ = "account_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
