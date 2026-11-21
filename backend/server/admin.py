import os
import logging
import secrets
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status, Depends
from dotenv import load_dotenv

from backend.server.session import current_session

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


@router.get("/debug/all-states", dependencies=[Depends(verify_admin_token)])
def get_all_debug_states():
    """
    Route sécurisée pour inspecter la partie en cours (ou la dernière terminée), sans rien cacher :
    - les joueurs, leur rôle, leur camp et la personnalité des IA ;
    - l'historique public et l'historique personnel de chaque agent (ce qu'il sait) ;
    - les actions de nuit de chaque joueur ;
    - les historiques des onglets Nuits et Votes du joueur humain.
    """
    return build_debug_state()


TEAM_LABELS = {"villageois": "Villageois", "outsider": "Outsider", "sbire": "Sbire", "demon": "Démon"}
def _moment(event) -> str:
    return f"{'Nuit' if event.phase.value == 'nuit' else 'Jour'} {event.turn}"


def _author(memory, event) -> str:
    return "Maître du Jeu" if event.author_id is None else memory.name_of(event.author_id)


def _channel(memory, event, reader: str) -> str:
    """Canal de l'événement, vu par `reader` : public, personnel ou privé (avec qui)."""
    if event.visible_to is None:
        return "public"
    if event.visible_to == {reader}:
        return "personnel"
    others = sorted(memory.name_of(p) for p in event.visible_to - {reader})
    return f"privé avec {', '.join(others)}"


def _night_history(session) -> list[dict]:
    """Onglet Nuits du joueur humain, avec des noms (le front du jeu, lui, reçoit des identifiants)."""
    history = []
    for entry in session.night_log:
        if entry.type == "result":
            dead = session.state.player(entry.dead_player).name if entry.dead_player else None
            info = f"{dead} est mort·e cette nuit." if dead else "Personne n'est mort cette nuit."
        else:
            info = entry.info
        history.append({"turn": entry.turn, "type": entry.type, "info": info})
    return history


def _vote_history(session) -> list[dict]:
    """Onglet Votes du joueur humain, avec des noms."""
    def name(player_id):
        return session.state.player(player_id).name if player_id else None
    return [
        {"turn": v.turn, "voter": name(v.voter), "target": name(v.target), "executed": name(v.executed)}
        for v in session.vote_log
    ]


def build_debug_state() -> dict:
    """État complet de la partie pour le panneau d'administration (noms, jamais d'identifiants)."""
    session = current_session()
    if session is None or session.state is None or session.memory is None:
        return {"game_in_progress": False, "message": "Aucune partie n'a encore été lancée."}

    state, memory, agents, human_id = session.state, session.memory, session.agents, session.human_id
    ai_ids = [p.id for p in state.players if p.id != human_id]

    return {
        "game_in_progress": session.running,
        "status": "en cours" if session.running else "terminée",
        "human": memory.name_of(human_id),
        "turn": state.turn,
        "phase": state.phase.value,
        "agents": [memory.name_of(pid) for pid in ai_ids],
        "channels": [", ".join(memory.name_of(pid) for pid in members)
                     for members in session.opened_channels.values()],
        "players": [
            {
                "name": p.name,
                "is_human": p.id == human_id,
                "role": p.role.name_FR,
                "team": TEAM_LABELS.get(p.role.team.value, p.role.team.value),
                "personality": getattr(agents.get(p.id), "personality_key", None),
                "alive": p.alive,
                "has_vote": p.can_vote,
            }
            for p in state.players
        ],
        # Tout ce qui s'est dit ou annoncé publiquement
        "public_history": [
            {"moment": _moment(e), "sender": _author(memory, e), "content": e.content}
            for e in memory.events_for(human_id) if e.visible_to is None
        ],
        # Historique personnel de chaque IA : tout ce qu'elle sait, dans l'ordre
        "agent_histories": {
            memory.name_of(pid): [
                {
                    "role": f"{_moment(e)} · {_channel(memory, e, pid)} · {_author(memory, e)}",
                    "content": e.content,
                }
                for e in memory.events_for(pid)
            ]
            for pid in ai_ids
        },
        # Action de nuit de chaque joueur (IA et humain), telle qu'enregistrée par le moteur
        "night_actions": sorted(
            (
                {"turn": e.turn, "player": p.name, "content": e.content}
                for p in state.players
                for e in memory.events_for(p.id)
                if e.type.value == "night_action" and e.visible_to == {p.id}
            ),
            key=lambda action: action["turn"],
        ),
        # Onglets Nuits et Votes du joueur humain
        "night_history": _night_history(session),
        "vote_history": _vote_history(session),
    }
