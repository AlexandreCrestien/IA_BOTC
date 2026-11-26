"""Signalements des messages des agents IA par les joueurs connectés (comptes seulement : rien n'est collecté
sur les invités), et leur suivi dans le panel admin.

Un signalement garde l'agent, sa personnalité, son rôle, le modèle qui a écrit le message (bascule comprise),
le message et le problème choisi. Il sert à améliorer les prompts à la main : il n'est jamais renvoyé aux agents
(un commentaire de joueur dans un prompt serait une porte ouverte à la manipulation).

Données personnelles (RGPD) :
- le pseudo du joueur, que les agents citent souvent, est remplacé par « [joueur] » dans le message enregistré ;
- à la suppression du compte, le signalement est détaché du compte et son commentaire effacé ;
- un signalement traité est supprimé 6 mois après son traitement (backend/accounts/service.py).
"""
import logging
import re
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from backend.db import AgentReport, get_session
from backend.db.models import utcnow
from backend.server.session import GameSession

logger = logging.getLogger(__name__)

# Problèmes proposés au joueur (mêmes libellés côté front : static/js/chat.js, REPORT_CATEGORIES)
REPORT_CATEGORIES = {
    "knowledge": "Révèle une information qu'il ne devrait pas connaître",
    "rules": "Incohérent ou contraire aux règles",
    "character": "Sort de son personnage",
    "inappropriate": "Contenu inapproprié",
    "other": "Autre",
}
COMMENT_MAX = 200        # commentaire facultatif
OTHER_COMMENT_MAX = 500  # « Autre » : commentaire obligatoire, qui décrit le problème
MAX_REPORTS_PER_GAME = 10
PLAYER_PLACEHOLDER = "[joueur]"

GUESTS_REFUSED = "Connectez-vous pour signaler un message : les signalements sont réservés aux comptes."
UNKNOWN_MESSAGE = "Ce message ne peut pas être signalé."
ALREADY_REPORTED = "Vous avez déjà signalé ce message."
TOO_MANY_REPORTS = f"Vous avez atteint la limite de {MAX_REPORTS_PER_GAME} signalements pour cette partie."
COMMENT_REQUIRED = "Décrivez le problème en quelques mots."
COMMENT_TOO_LONG = "Commentaire trop long ({max} caractères au plus)."
NOT_SAVED = "Le signalement n'a pas pu être enregistré. Réessayez plus tard."


def without_pseudo(text: str, pseudo: str) -> str:
    """Remplace le pseudo du joueur par « [joueur] » (mot entier, sans tenir compte de la casse)."""
    return re.sub(rf"(?<!\w){re.escape(pseudo)}(?!\w)", PLAYER_PLACEHOLDER, text, flags=re.IGNORECASE)


def report_error(session: GameSession, message_id: str, category: str, comment: Optional[str]) -> Optional[str]:
    """Motif du refus, ou None si le signalement peut être enregistré."""
    if session.user_id is None:
        return GUESTS_REFUSED
    entry = session.ai_messages.get(message_id)
    if entry is None:
        return UNKNOWN_MESSAGE
    if entry["message"].reported:
        return ALREADY_REPORTED
    if session.reports_sent >= MAX_REPORTS_PER_GAME:
        return TOO_MANY_REPORTS
    limit = OTHER_COMMENT_MAX if category == "other" else COMMENT_MAX
    if category == "other" and not comment:
        return COMMENT_REQUIRED
    if comment and len(comment) > limit:
        return COMMENT_TOO_LONG.format(max=limit)
    return None


def save_report(session: GameSession, message_id: str, category: str, comment: Optional[str]) -> Optional[str]:
    """Enregistre le signalement d'un message d'agent IA. Renvoie le motif du refus, ou None s'il est enregistré."""
    comment = (comment or "").strip() or None
    error = report_error(session, message_id, category, comment)
    if error is not None:
        return error
    entry = session.ai_messages[message_id]
    agent_id = entry["agent"]
    player = session.state.player(agent_id)
    agent = session.agents.get(agent_id)
    report = AgentReport(
        user_id=session.user_id,
        game_id=session.record_id,
        agent=player.name,
        personality=getattr(agent, "personality_key", None) or "inconnue",
        role=player.role.name_EN,
        model=entry["model"],
        channel=entry["channel"],
        moment=f"{'Nuit' if entry['phase'] == 'nuit' else 'Jour'} {entry['turn']}",
        message=without_pseudo(entry["message"].content, session.state.player(session.human_id).name),
        category=category,
        comment=comment,
        created_at=utcnow(),
    )
    try:
        with get_session() as db:
            db.add(report)
            db.commit()
    except SQLAlchemyError:
        logger.exception("Signalement du message %s non enregistré", message_id)
        return NOT_SAVED
    entry["message"].reported = True  # renvoyé ainsi à la reconnexion
    session.reports_sent += 1
    logger.info("Message %s de %s signalé (%s)", message_id, player.name, category)
    return None
