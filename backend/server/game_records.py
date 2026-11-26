"""Enregistrement de la partie en cours dans la base, pour les statistiques du compte du joueur.

- Joueur connecté : la partie est enregistrée « en cours » dès sa mise en place, puis clôturée
  (victoire, défaite, défaite par abandon, ou interrompue si elle plante).
- Invité : rien n'est enregistré. S'il s'inscrit ou se connecte pendant la partie, ou sur l'écran de fin,
  il présente le guest_token reçu à la connexion et la partie est rattachée à son compte (claim_guest_game).

À la fin d'une partie gagnée ou perdue d'un compte, les succès obtenus sont débloqués (backend/stats)
et gardés dans la session (session.unlocked) pour être annoncés sur l'écran de fin.
À la fin de toute partie d'un compte, son détail complet est enregistré pour le panel admin (GameDetail).

Une erreur de base de données est journalisée mais n'interrompt jamais la partie.
"""
import logging
import secrets
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db import GameDetail, GameRecord, GameStatus, get_session
from backend.db.models import utcnow
from backend.models import Alignment, GameState
from backend.server.game_view import game_view
from backend.server.session import GameSession, current_session
from backend.stats.achievements import GameSummary, earned_achievements
from backend.stats.queries import achievement_out, unlock

logger = logging.getLogger(__name__)

# Issues d'une partie terminée qu'un invité peut rattacher à son compte depuis l'écran de fin
CLAIMABLE_OUTCOMES = (GameStatus.WON, GameStatus.LOST)


def new_guest_token() -> str:
    return secrets.token_urlsafe(16)


def outcome_for(state: GameState, human_id: str, winner: Alignment) -> GameStatus:
    """Victoire ou défaite du joueur humain, selon le camp vainqueur."""
    return GameStatus.WON if state.player(human_id).role.alignment == winner else GameStatus.LOST


def _unlock_achievements(db: Session, session: GameSession, record: GameRecord) -> None:
    """Partie terminée normalement (victoire ou défaite) : débloque les succès obtenus.
    Abandon ou interruption : aucun succès."""
    if record.status not in CLAIMABLE_OUTCOMES:
        return
    summary = GameSummary(role=record.role, won=record.status == GameStatus.WON, turns=record.turns,
                          facts=session.facts)
    new = unlock(db, record.user_id, record.id, earned_achievements(summary))
    session.unlocked = [achievement_out(a, unlocked_at=utcnow()) for a in new]


# Statut affiché dans le détail enregistré (le panel admin le montre comme une partie terminée)
STATUS_LABELS = {GameStatus.WON: "victoire", GameStatus.LOST: "défaite", GameStatus.ABANDONED: "abandonnée",
                 GameStatus.INTERRUPTED: "interrompue"}


def _save_detail(db: Session, session: GameSession, record: GameRecord) -> None:
    """Fin de partie d'un compte : enregistre son détail complet pour le panel admin (débogage, service client).
    Jamais pour une partie anonymisée (compte supprimé) ; supprimé avec le compte et au bout de 6 mois."""
    if record.user_id is None or record.status == GameStatus.IN_PROGRESS:
        return
    view = game_view(session)
    if view is None or db.query(GameDetail).filter_by(game_id=record.id).first() is not None:
        return
    view.update(game_in_progress=False, status=STATUS_LABELS.get(record.status, "terminée"), turn=record.turns)
    db.add(GameDetail(game_id=record.id, data=view, created_at=utcnow()))


def open_record(session: GameSession) -> None:
    """Crée la ligne de la partie pour le compte du joueur (une seule fois, une fois la partie mise en place).
    Partie déjà terminée (invité inscrit sur l'écran de fin) : la ligne est créée directement avec son issue."""
    if session.user_id is None or session.record_id is not None or session.state is None:
        return
    role = session.state.player(session.human_id).role
    try:
        with get_session() as db:
            record = GameRecord(
                user_id=session.user_id, role=role.name_EN, alignment=role.alignment,
                started_at=session.started_at, turns=session.state.turn,
                status=session.outcome or GameStatus.IN_PROGRESS, ended_at=session.ended_at,
            )
            db.add(record)
            db.flush()
            _unlock_achievements(db, session, record)  # partie déjà terminée (inscription sur l'écran de fin)
            _save_detail(db, session, record)
            db.commit()
            session.record_id = record.id
    except SQLAlchemyError:
        logger.exception("Partie non enregistrée pour le compte %s", session.user_id)


def close_record(session: GameSession, status: GameStatus, turns: Optional[int] = None) -> None:
    """Fin de partie : garde l'issue dans la session et met à jour la ligne de la partie, s'il y en a une."""
    session.outcome = status
    session.ended_at = utcnow()
    if turns is None:
        turns = session.state.turn if session.state is not None else 0
    if session.record_id is None:
        return
    try:
        with get_session() as db:
            record = db.get(GameRecord, session.record_id)
            if record is None:  # compte supprimé entre-temps
                return
            record.status, record.turns, record.ended_at = status, turns, session.ended_at
            _unlock_achievements(db, session, record)
            _save_detail(db, session, record)
            db.commit()
    except SQLAlchemyError:
        logger.exception("Issue de la partie %s non enregistrée", session.record_id)


def claim_guest_game(user_id: int, guest_token: Optional[str]) -> bool:
    """Rattache la partie de l'invité au compte qui vient de s'inscrire ou de se connecter.
    Possible pendant la partie, ou après une victoire ou une défaite tant qu'aucune autre partie n'a commencé.
    Renvoie True si la partie a été rattachée."""
    session = current_session()
    if (not guest_token or session is None or session.user_id is not None or session.guest_token is None
            or not secrets.compare_digest(guest_token.encode(), session.guest_token.encode())):
        return False
    if not session.running and session.outcome not in CLAIMABLE_OUTCOMES:
        return False  # partie plantée : jamais comptée
    session.user_id = user_id
    session.guest_token = None  # usage unique
    open_record(session)  # si la partie n'est pas encore mise en place, run_game l'enregistrera
    logger.info("Partie de l'invité %s rattachée au compte %s", session.human_id, user_id)
    return True
