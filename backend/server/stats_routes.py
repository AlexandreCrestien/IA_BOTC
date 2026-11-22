"""Routes du tableau de bord : statistiques, historique des parties et succès du compte connecté."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import User
from backend.server.auth import current_user, db_session
from backend.stats.queries import achievements_of, game_history, player_stats

router = APIRouter(prefix="/api/me", tags=["Statistiques"])


@router.get("/stats")
def stats(user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
    """Parties jouées, victoires et part de victoires (au total, côté villageois, côté démons), tours moyens.
    Comptées : victoires, défaites et abandons (défaites). Les parties interrompues ne comptent pas."""
    return player_stats(db, user.id)


@router.get("/games")
def games(user: User = Depends(current_user), db: Session = Depends(db_session)) -> list[dict]:
    """Parties terminées ou interrompues, de la plus récente à la plus ancienne : date, rôle, camp, issue, tours."""
    return game_history(db, user.id)


@router.get("/achievements")
def achievements(user: User = Depends(current_user), db: Session = Depends(db_session)) -> list[dict]:
    """Tous les succès ; un succès caché non débloqué est renvoyé sans titre ni description (« ??? »)."""
    return achievements_of(db, user.id)
