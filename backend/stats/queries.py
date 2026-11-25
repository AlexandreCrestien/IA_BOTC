"""Lecture et écriture des statistiques et des succès d'un compte.

Statistiques : parties gagnées, perdues et abandonnées (une partie abandonnée est une défaite).
Les parties interrompues (serveur arrêté ou planté) apparaissent dans l'historique mais ne comptent pas.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import (
    COUNTED_STATUSES,
    AccountEvent,
    GameDetail,
    GameRecord,
    GameStatus,
    UnlockedAchievement,
    User,
    iso_utc,
)
from backend.db.models import utcnow
from backend.models import Alignment
from backend.rules import get_role
from backend.stats.achievements import ACHIEVEMENTS, BY_CODE, Achievement

HIDDEN_TITLE = "???"
HIDDEN_DESCRIPTION = "Succès caché."


def unlock(db: Session, user_id: int, game_id: int, achievements: list[Achievement]) -> list[Achievement]:
    """Enregistre les succès pas encore débloqués par ce compte ; renvoie ceux qui viennent de l'être.
    L'appelant valide (commit)."""
    owned = set(db.scalars(select(UnlockedAchievement.code).where(UnlockedAchievement.user_id == user_id)))
    new = [a for a in achievements if a.code not in owned]
    db.add_all(UnlockedAchievement(user_id=user_id, code=a.code, game_id=game_id) for a in new)
    return new


def _ratio(wins: int, played: int) -> Optional[float]:
    """Part de victoires entre 0 et 1 (None sans partie jouée)."""
    return round(wins / played, 3) if played else None


def _summary(games: list[GameRecord]) -> dict:
    wins = sum(1 for g in games if g.status == GameStatus.WON)
    return {"played": len(games), "wins": wins, "win_rate": _ratio(wins, len(games))}


def player_stats(db: Session, user_id: int) -> dict:
    """Statistiques générales : parties jouées, victoires (au total, côté villageois, côté démons), tours moyens."""
    games = list(db.scalars(select(GameRecord).where(
        GameRecord.user_id == user_id, GameRecord.status.in_(COUNTED_STATUSES))))
    return {
        **_summary(games),
        "good": _summary([g for g in games if g.alignment == Alignment.GOOD]),
        "evil": _summary([g for g in games if g.alignment == Alignment.EVIL]),
        "average_turns": round(sum(g.turns for g in games) / len(games), 1) if games else None,
    }


def game_history(db: Session, user_id: int) -> list[dict]:
    """Parties terminées (ou interrompues), de la plus récente à la plus ancienne. La partie en cours n'y est pas."""
    games = db.scalars(select(GameRecord)
                       .where(GameRecord.user_id == user_id, GameRecord.status != GameStatus.IN_PROGRESS)
                       .order_by(GameRecord.started_at.desc(), GameRecord.id.desc()))
    return [
        {
            "id": g.id,
            "date": iso_utc(g.started_at),
            "role": g.role.value,
            "role_name": get_role(g.role).name_FR,
            "alignment": g.alignment.value,
            "status": g.status.value,   # won | lost | abandoned | interrupted
            "counted": g.status in COUNTED_STATUSES,
            "turns": g.turns,
        }
        for g in games
    ]


def achievement_out(achievement: Achievement, unlocked_at: Optional[datetime] = None) -> dict:
    """Succès pour le front. Caché et pas encore débloqué : ni titre, ni description, ni message."""
    unlocked = unlocked_at is not None
    secret = achievement.hidden and not unlocked
    return {
        "code": achievement.code,
        "title": HIDDEN_TITLE if secret else achievement.title,
        "description": HIDDEN_DESCRIPTION if secret else achievement.description,
        "message": achievement.message if unlocked else None,
        "hidden": achievement.hidden,
        "unlocked": unlocked,
        "unlocked_at": iso_utc(unlocked_at) if unlocked else None,
    }


def achievements_of(db: Session, user_id: int) -> list[dict]:
    """Tous les succès, débloqués ou non, dans l'ordre de leur définition."""
    unlocked = dict(db.execute(select(UnlockedAchievement.code, UnlockedAchievement.unlocked_at)
                               .where(UnlockedAchievement.user_id == user_id)).all())
    return [achievement_out(a, unlocked.get(a.code)) for a in ACHIEVEMENTS]


STATUS_LABELS = {
    GameStatus.IN_PROGRESS: "en cours",
    GameStatus.WON: "victoire",
    GameStatus.LOST: "défaite",
    GameStatus.ABANDONED: "défaite (abandon)",
    GameStatus.INTERRUPTED: "interrompue (non comptée)",
}
ALIGNMENT_LABELS = {Alignment.GOOD: "Villageois", Alignment.EVIL: "Démons"}


def export_account(db: Session, user: User) -> dict:
    """Copie de toutes les données du compte (droit d'accès du RGPD), lisible par une personne :
    compte, registre de ses modifications, parties (partie en cours comprise, avec leur détail tant qu'il est
    gardé), succès débloqués et statistiques.
    Ni le mot de passe (seule son empreinte est stockée, jamais exportée) ni la version de jeton."""
    from backend.accounts.service import ACCOUNT_EVENTS  # import local : le service des comptes importe ce module
    games = list(db.scalars(select(GameRecord).where(GameRecord.user_id == user.id)
                            .order_by(GameRecord.started_at, GameRecord.id)))
    details = {d.game_id: d.data for d in db.scalars(
        select(GameDetail).where(GameDetail.game_id.in_([g.id for g in games])))}
    events = db.scalars(select(AccountEvent).where(AccountEvent.user_id == user.id)
                        .order_by(AccountEvent.created_at, AccountEvent.id))
    unlocked = db.scalars(select(UnlockedAchievement).where(UnlockedAchievement.user_id == user.id)
                          .order_by(UnlockedAchievement.unlocked_at, UnlockedAchievement.id))
    return {
        "export": {
            "service": "Lantern Hollow",
            "generated_at": iso_utc(utcnow()),
            "contents": "Toutes les données enregistrées pour votre compte. Les dates sont en UTC.",
            "retention": "Le détail de chaque partie (messages, votes, actions, mémoire des personnages) est gardé "
                         "6 mois pour le service client ; le registre des modifications du compte, un an. Votre mot "
                         "de passe n'est pas stocké : seule une empreinte chiffrée l'est, et elle n'est pas exportée.",
        },
        "account": {
            "pseudo": user.pseudo,
            "email": user.email,
            "email_verified_at": iso_utc(user.email_verified_at) if user.email_verified_at else None,
            "type": "administrateur" if user.is_admin else "joueur",
            "created_at": iso_utc(user.created_at),
            "last_activity_at": iso_utc(user.last_seen_at),
        },
        "account_history": [
            {"event": ACCOUNT_EVENTS.get(e.kind, e.kind), "date": iso_utc(e.created_at)} for e in events
        ],
        "games": [
            {
                "started_at": iso_utc(g.started_at),
                "ended_at": iso_utc(g.ended_at) if g.ended_at else None,
                "role": get_role(g.role).name_FR,
                "side": ALIGNMENT_LABELS[g.alignment],
                "result": STATUS_LABELS[g.status],
                "turns": g.turns,
                "detail": details.get(g.id),  # déroulé complet, tant qu'il est gardé (6 mois)
            }
            for g in games
        ],
        "achievements": [
            {
                "title": BY_CODE[a.code].title if a.code in BY_CODE else a.code,
                "description": BY_CODE[a.code].description if a.code in BY_CODE else None,
                "unlocked_at": iso_utc(a.unlocked_at),
            }
            for a in unlocked
        ],
        "statistics": player_stats(db, user.id),
    }

