"""Routes du panneau d'administration, réservées au compte admin (cookie de connexion, voir auth.py) :
état complet de la partie en cours, comptes (réinitialisation du mot de passe, suppression), parties passées
d'un joueur avec leur détail, registre des modifications d'un compte, signalements des messages des IA."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounts import service
from backend.accounts.service import AccountError
from backend.db import AccountEvent, AgentReport, GameDetail, GameRecord, User, iso_utc
from backend.db.models import utcnow
from backend.rules import get_role
from backend.server.auth import admin_user, db_session, notify_password_changed
from backend.server.account_removal import remove_account
from backend.server.game_view import game_view
from backend.server.reports import REPORT_CATEGORIES
from backend.server.session import current_session

logger = logging.getLogger(__name__)

# Toutes les routes : 401 sans connexion, 403 pour un compte qui n'est pas admin
router = APIRouter(prefix="/admin", tags=["Administration"], dependencies=[Depends(admin_user)])


@router.get("/users")
def list_users(db: Session = Depends(db_session)) -> list[dict]:
    """Comptes, du plus ancien au plus récent (jamais le hash du mot de passe)."""
    users = db.scalars(select(User).order_by(User.created_at, User.id)).all()
    return [{"id": u.id, "pseudo": u.pseudo, "email": u.email, "email_verified": u.email_verified,
             "is_admin": u.is_admin,
             "created_at": iso_utc(u.created_at)}
            for u in users]


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(user_id: int, db: Session = Depends(db_session)) -> dict:
    """Dépannage d'un joueur qui a oublié son mot de passe : mot de passe temporaire, montré une seule fois
    à l'admin qui le lui transmet. Le joueur est déconnecté partout et prévenu par e-mail."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")
    try:
        temporary = service.reset_password(db, user)
    except AccountError as error:
        raise HTTPException(error.status, error.message)
    await notify_password_changed(user, "par l'administrateur")
    return {"pseudo": user.pseudo, "temporary_password": temporary}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Session = Depends(db_session)) -> None:
    """Suppression d'un compte à la demande du joueur (même suppression que depuis son tableau de bord) :
    compte et succès effacés, parties gardées anonymement. Sa partie en cours est arrêtée d'abord."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")
    try:
        await remove_account(db, user, reason="par l'admin")
    except AccountError as error:
        raise HTTPException(error.status, error.message)


def _user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")
    return user


def _game_summary(game: GameRecord, has_detail: bool) -> dict:
    return {"id": game.id, "date": iso_utc(game.started_at), "role_name": get_role(game.role).name_FR,
            "alignment": game.alignment.value, "status": game.status.value, "turns": game.turns,
            "has_detail": has_detail}


@router.get("/users/{user_id}/games")
def user_games(user_id: int, db: Session = Depends(db_session)) -> list[dict]:
    """Parties d'un joueur, de la plus récente à la plus ancienne ; has_detail : détail encore disponible
    (effacé au bout de 6 mois)."""
    _user_or_404(db, user_id)
    games = db.scalars(select(GameRecord).where(GameRecord.user_id == user_id)
                       .order_by(GameRecord.started_at.desc(), GameRecord.id.desc())).all()
    with_detail = set(db.scalars(select(GameDetail.game_id).where(GameDetail.game_id.in_([g.id for g in games]))))
    return [_game_summary(g, g.id in with_detail) for g in games]


@router.get("/games/{game_id}")
def game_detail(game_id: int, db: Session = Depends(db_session)) -> dict:
    """Détail complet d'une partie passée (même forme que /debug/all-states), avec son résumé et son joueur."""
    game = db.get(GameRecord, game_id)
    detail = db.scalar(select(GameDetail).where(GameDetail.game_id == game_id))
    if game is None or detail is None or game.user_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Détail introuvable : partie inconnue, ou détail effacé (plus de 6 mois).")
    return {"game": {**_game_summary(game, True), "pseudo": game.user.pseudo}, "detail": detail.data}


@router.get("/users/{user_id}/events")
def user_events(user_id: int, db: Session = Depends(db_session)) -> list[dict]:
    """Registre des modifications du compte (type et date, gardé un an), du plus récent au plus ancien."""
    _user_or_404(db, user_id)
    events = db.scalars(select(AccountEvent).where(AccountEvent.user_id == user_id)
                        .order_by(AccountEvent.created_at.desc(), AccountEvent.id.desc())).all()
    return [{"kind": e.kind, "label": service.ACCOUNT_EVENTS.get(e.kind, e.kind), "date": iso_utc(e.created_at)}
            for e in events]


def _game_link(game_id, with_detail: set[int]):
    """Partie d'un signalement : "detail" (détail enregistré), "current" (partie en cours ou dernière terminée,
    pas encore enregistrée) ou None (partie d'un compte supprimé, ou détail effacé au bout de 6 mois)."""
    if game_id is None:
        return None
    if game_id in with_detail:
        return "detail"
    session = current_session()
    return "current" if session is not None and session.record_id == game_id else None


@router.get("/reports")
def list_reports(db: Session = Depends(db_session)) -> list[dict]:
    """Signalements des messages des IA, du plus récent au plus ancien (filtrés par le panel)."""
    reports = db.scalars(select(AgentReport).order_by(AgentReport.created_at.desc(), AgentReport.id.desc())).all()
    game_ids = {r.game_id for r in reports if r.game_id is not None}
    with_detail = set(db.scalars(select(GameDetail.game_id).where(GameDetail.game_id.in_(game_ids))))
    pseudos = dict(db.execute(select(User.id, User.pseudo).where(
        User.id.in_({r.user_id for r in reports if r.user_id is not None}))).all())
    return [
        {
            "id": r.id, "date": iso_utc(r.created_at), "agent": r.agent, "personality": r.personality,
            "role_name": get_role(r.role).name_FR, "model": r.model, "channel": r.channel, "moment": r.moment,
            "message": r.message, "category": r.category, "category_label": REPORT_CATEGORIES.get(r.category, r.category),
            "comment": r.comment, "reporter": pseudos.get(r.user_id),  # None : compte supprimé
            "handled": r.handled_at is not None,
            "handled_at": iso_utc(r.handled_at) if r.handled_at else None,
            "game_id": r.game_id, "game_link": _game_link(r.game_id, with_detail),
        }
        for r in reports
    ]


class ReportStatus(BaseModel):
    handled: bool


@router.put("/reports/{report_id}/status")
def set_report_status(report_id: int, body: ReportStatus, db: Session = Depends(db_session)) -> dict:
    """Marque un signalement comme traité (supprimé 6 mois plus tard) ou le remet en attente."""
    report = db.get(AgentReport, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signalement introuvable.")
    report.handled_at = utcnow() if body.handled else None
    db.commit()
    return {"id": report.id, "handled": body.handled,
            "handled_at": iso_utc(report.handled_at) if report.handled_at else None}


@router.get("/debug/all-states")
def get_all_debug_states():
    """
    Route sécurisée pour inspecter la partie en cours (ou la dernière terminée), sans rien cacher :
    - les joueurs, leur rôle, leur camp et la personnalité des IA ;
    - l'historique public et l'historique personnel de chaque agent (ce qu'il sait) ;
    - les actions de nuit de chaque joueur ;
    - les historiques des onglets Nuits et Votes du joueur humain.
    """
    return build_debug_state()


def build_debug_state() -> dict:
    """État complet de la partie en cours (ou de la dernière terminée) pour le panneau d'administration."""
    session = current_session()
    view = game_view(session) if session is not None else None
    if view is None:
        return {"game_in_progress": False, "message": "Aucune partie n'a encore été lancée."}
    return view
