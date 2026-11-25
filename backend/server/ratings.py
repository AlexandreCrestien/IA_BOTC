"""Évaluation des agents IA par le joueur connecté, sur l'écran de fin d'une partie terminée (victoire ou défaite) :
une note de 1 à 5 par agent (« ce personnage était-il crédible ? ») et un commentaire facultatif.
Une seule évaluation par partie, réservée aux comptes : rien n'est collecté sur les invités.

Chaque note garde l'agent, sa personnalité, son rôle et le modèle qui a écrit le plus de ses messages dans la partie
(la note porte surtout sur sa façon de parler ; ses votes et actions de nuit passent par d'autres modèles).
Comme les signalements, les évaluations ne sont jamais renvoyées aux agents.

Données personnelles (RGPD) : à la suppression du compte, l'évaluation est détachée du compte et son commentaire
effacé ; le commentaire est aussi effacé au bout de 6 mois (backend/accounts/service.py), la note est gardée.
"""
import logging
from collections import Counter
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from backend.db import AgentRating, get_session
from backend.db.models import utcnow
from backend.server.game_records import CLAIMABLE_OUTCOMES
from backend.server.reports import without_pseudo
from backend.server.session import GameSession

logger = logging.getLogger(__name__)

COMMENT_MAX = 300

GUESTS_REFUSED = "Connectez-vous pour évaluer les agents : les évaluations sont réservées aux comptes."
NOT_FINISHED = "Les agents s'évaluent à la fin d'une partie terminée."
ALREADY_RATED = "Vous avez déjà évalué les agents de cette partie."
UNKNOWN_AGENT = "Agent inconnu dans cette partie."
DUPLICATE_AGENT = "Chaque agent ne peut être évalué qu'une fois."
NOT_SAVED = "L'évaluation n'a pas pu être enregistrée. Réessayez plus tard."


def main_model(session: GameSession, agent_id: str) -> Optional[str]:
    """Modèle qui a écrit le plus de messages de l'agent dans la partie (None s'il n'a rien dit)."""
    models = Counter(m["model"] for m in session.ai_messages.values() if m["agent"] == agent_id and m["model"])
    return models.most_common(1)[0][0] if models else None


def rating_error(session: GameSession, ratings: list) -> Optional[str]:
    """Motif du refus, ou None si l'évaluation peut être enregistrée. ratings : AgentRatingIn (schemas.py)."""
    if session.user_id is None:
        return GUESTS_REFUSED
    if session.running or session.outcome not in CLAIMABLE_OUTCOMES:
        return NOT_FINISHED
    if session.rated:
        return ALREADY_RATED
    agent_ids = [r.agent_id for r in ratings]
    if any(agent_id not in session.agents for agent_id in agent_ids):
        return UNKNOWN_AGENT
    if len(set(agent_ids)) != len(agent_ids):
        return DUPLICATE_AGENT
    return None


def save_ratings(session: GameSession, ratings: list) -> Optional[str]:
    """Enregistre l'évaluation des agents. Renvoie le motif du refus, ou None si elle est enregistrée."""
    error = rating_error(session, ratings)
    if error is not None:
        return error
    pseudo = session.state.player(session.human_id).name
    now = utcnow()
    rows = []
    for rating in ratings:
        player = session.state.player(rating.agent_id)
        comment = (rating.comment or "").strip()
        rows.append(AgentRating(
            user_id=session.user_id,
            game_id=session.record_id,
            agent=player.name,
            personality=getattr(session.agents[rating.agent_id], "personality_key", None) or "inconnue",
            role=player.role.name_EN,
            model=main_model(session, rating.agent_id),
            score=rating.score,
            comment=without_pseudo(comment, pseudo) if comment else None,
            created_at=now,
        ))
    try:
        with get_session() as db:
            db.add_all(rows)
            db.commit()
    except SQLAlchemyError:
        logger.exception("Évaluation des agents non enregistrée")
        return NOT_SAVED
    session.rated = True
    logger.info("Agents évalués par le compte %s (%d note(s))", session.user_id, len(rows))
    return None
