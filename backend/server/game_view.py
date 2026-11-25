"""Vue complète d'une partie, sans rien cacher : joueurs et rôles, personnalités, historique public,
mémoire de chaque IA, actions de nuit, IA indisponibles, onglets Nuits et Votes du joueur humain.

Pour le panel admin uniquement (débogage, service client) : jamais montrée aux joueurs.
"""
from typing import Optional

from backend.server.session import GameSession

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


def game_view(session: GameSession) -> Optional[dict]:
    """État complet d'une partie (noms, jamais d'identifiants), ou None si elle n'est pas encore mise en place.
    Montré par le panel admin pour la partie en cours, et enregistré à la fin des parties des comptes
    (game_records.py) pour être consulté ensuite."""
    if session.state is None or session.memory is None:
        return None

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
