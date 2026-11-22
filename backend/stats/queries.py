"""Lecture et écriture des statistiques et des succès d'un compte.

Statistiques : parties gagnées, perdues et abandonnées (une partie abandonnée est une défaite).
Les parties interrompues (serveur arrêté ou planté) apparaissent dans l'historique mais ne comptent pas.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import COUNTED_STATUSES, GameRecord, GameStatus, UnlockedAchievement, iso_utc
from backend.models import Alignment
from backend.rules import get_role
from backend.stats.achievements import ACHIEVEMENTS, Achievement

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
