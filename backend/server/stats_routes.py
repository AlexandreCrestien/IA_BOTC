"""Routes du tableau de bord : statistiques, historique des parties, succès et export des données du compte connecté."""
import json
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.db import User
from backend.server.auth import current_user, db_session
from backend.stats.queries import achievements_of, export_account, game_history, player_stats

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


@router.get("/export")
def export(user: User = Depends(current_user), db: Session = Depends(db_session)) -> Response:
    """Téléchargement de toutes les données du compte (droit d'accès du RGPD), en fichier JSON indenté,
    lisible dans un éditeur de texte."""
    filename = f"lantern-hollow-mes-donnees-{date.today().isoformat()}.json"
    content = json.dumps(export_account(db, user), ensure_ascii=False, indent=2)
    return Response(content, media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

