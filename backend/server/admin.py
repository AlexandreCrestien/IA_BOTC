import os
import logging
import secrets
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status, Depends
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Administration"])

ADMIN_SECRET_TOKEN = os.getenv("ADMIN_SECRET_TOKEN")

def verify_admin_token(x_admin_token: Optional[str] = Header(default=None)):
    """Vérifie que la requête contient le bon jeton secret dans le header.
    Si aucun jeton n'est configuré (variable absente ou vide), l'accès admin est toujours refusé.
    Header absent ou jeton faux : même réponse 403.
    compare_digest compare en temps constant : le temps de réponse ne révèle rien du jeton.
    On compare des octets : avec du texte, un caractère non ASCII ferait planter la comparaison."""
    if not ADMIN_SECRET_TOKEN or not x_admin_token or not secrets.compare_digest(x_admin_token.encode(), ADMIN_SECRET_TOKEN.encode()):
        logger.warning("Tentative d'accès admin non autorisée détectée.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : Jeton admin invalide ou manquant."
        )
    return x_admin_token


def _event_view(memory, event) -> dict:
    return {
        "turn": event.turn,
        "phase": event.phase.value,
        "type": event.type.value,
        "author": "Maître du Jeu" if event.author_id is None else memory.name_of(event.author_id),
        "visible_to": "tous" if event.visible_to is None else sorted(memory.name_of(p) for p in event.visible_to),
        "content": event.content,
    }


def session_debug_view(player_id: str, session) -> dict:
    """Tout ce qui est caché aux joueurs : rôles, effets, personnalités et la mémoire complète."""
    state, memory = session.state, session.memory
    view = {"player": player_id, "finished": session.finished}
    if state is None or memory is None:
        return {**view, "status": "partie en préparation"}
    agents = session.agents
    return {
        **view,
        "turn": state.turn,
        "phase": state.phase.value,
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "role": p.role.name_FR,
                "team": p.role.team.value,
                "alive": p.alive,
                "can_vote": p.can_vote,
                "effects": [e.type.value for e in p.effects],
                "links": dict(p.links),
                "personality": agents[p.id].personality_key if p.id in agents else "humain",
            }
            for p in state.players
        ],
        "events": [_event_view(memory, e) for e in memory._events],
    }


@router.get("/debug/all-states", dependencies=[Depends(verify_admin_token)])
def get_all_debug_states():
    """
    Route sécurisée pour l'inspection totale des parties en cours :
    rôles et effets de tous les joueurs, personnalités des agents,
    et historique complet (public, privé, nuits) avec qui pouvait voir quoi.
    """
    from backend.server.websockets import sessions  # import tardif : évite une importation circulaire
    return {
        "status": "success",
        "games": [session_debug_view(player_id, session) for player_id, session in sessions.items()],
    }
