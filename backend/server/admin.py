"""Routes du panneau d'administration, réservées au compte admin (cookie de connexion, voir auth.py) :
état complet de la partie en cours, liste des comptes et réinitialisation d'un mot de passe."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounts import service
from backend.accounts.service import AccountError
from backend.db import User, iso_utc
from backend.server.auth import admin_user, db_session
from backend.server.session import current_session

logger = logging.getLogger(__name__)

# Toutes les routes : 401 sans connexion, 403 pour un compte qui n'est pas admin
router = APIRouter(prefix="/admin", tags=["Administration"], dependencies=[Depends(admin_user)])


@router.get("/users")
def list_users(db: Session = Depends(db_session)) -> list[dict]:
    """Comptes, du plus ancien au plus récent (jamais le hash du mot de passe)."""
    users = db.scalars(select(User).order_by(User.created_at, User.id)).all()
    return [{"id": u.id, "pseudo": u.pseudo, "is_admin": u.is_admin, "created_at": iso_utc(u.created_at)}
            for u in users]


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, db: Session = Depends(db_session)) -> dict:
    """Dépannage d'un joueur qui a oublié son mot de passe : mot de passe temporaire, montré une seule fois
    à l'admin qui le lui transmet. Le joueur est déconnecté partout."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")
    try:
        temporary = service.reset_password(db, user)
    except AccountError as error:
        raise HTTPException(error.status, error.message)
    return {"pseudo": user.pseudo, "temporary_password": temporary}


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


TEAM_LABELS = {"townsfolk": "Villageois", "outcast": "Paria", "accomplice": "Complice", "demon": "Démon"}
FAILURE_STEPS = {"night": "action de nuit (choix tiré au hasard)", "public": "message public",
                 "private": "réponse en salon privé", "vote": "vote (abstention)"}
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
        # IA qui n'ont pas répondu (les échecs de nuit ne sont montrés qu'ici)
        "agent_failures": [
            {
                "moment": f"{'Nuit' if f['phase'] == 'nuit' else 'Jour'} {f['turn']}",
                "agent": memory.name_of(f["agent"]),
                "step": FAILURE_STEPS.get(f["step"], f["step"]),
            }
            for f in session.agent_failures
        ],
        # Onglets Nuits et Votes du joueur humain
        "night_history": _night_history(session),
        "vote_history": _vote_history(session),
    }
