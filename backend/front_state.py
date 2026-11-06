"""Adaptateur : transforme l'état de la partie au format attendu par le front (app.js).
Il ne calcule aucune règle, il présente ce que le moteur et la mémoire contiennent déjà."""
from backend.memory_manager import MemoryManager
from backend.models import EventType, GameState
from backend.models.enums import Phase
from backend.rules.actions import legal_actions

PHASE_FRONT = {Phase.NUIT: "night", Phase.DISCUSSION: "day", Phase.VOTE: "vote"}
PUBLIC_CHANNEL = "public"


def whisper_channel_id(member_ids) -> str:
    """Même format que le serveur : whisper_<ids triés>."""
    return "whisper_" + "_".join(sorted(member_ids))


def to_front_state(
    state: GameState,
    memory: MemoryManager,
    human_id: str,
    votes_history: tuple[dict, ...] = (),
) -> dict:
    """votes_history : un élément par tour, {"turn": int, "votes": {id_votant: id_cible ou None},
    "executed": id ou None}. Fourni par l'appelant, qui le garde à chaque tour."""
    me = state.player(human_id)
    legal = legal_actions(state, human_id) if state.phase == Phase.NUIT else None

    def name(pid):
        return None if pid is None else state.player(pid).name

    return {
        "day": state.turn,
        "phase": PHASE_FRONT[state.phase],
        "aliveCount": len(state.alive_players()),
        "me": {"id": me.id, "name": me.name, "alive": me.alive, "canVote": me.can_vote},
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "alive": p.alive,
                "suspicion": "",
                "lastVote": _last_vote(p.id, votes_history, name),
            }
            for p in state.players
        ],
        "nightTargets": [{"id": t, "name": name(t)} for t in legal.targets] if legal else [],
        "nightCount": legal.count if legal else 0,
        "messages": _messages(memory, human_id, name),
        "nightHistory": _night_history(memory, human_id),
        "votesHistory": [_vote_entry(entry, name) for entry in votes_history],
    }


def _last_vote(player_id, votes_history, name):
    """Dernier vote émis par ce joueur. None = n'a jamais voté (« Non utilisé » côté front)."""
    for entry in reversed(votes_history):
        if player_id in entry["votes"]:
            target = entry["votes"][player_id]
            return "Personne" if target is None else name(target)
    return None


def _messages(memory, human_id, name) -> dict:
    """Messages par canal, au format attendu par le front : {canal: [{sender, content}]}."""
    messages: dict[str, list[dict]] = {}
    for event in memory.events_for(human_id):
        if event.type == EventType.public_message:
            channel = PUBLIC_CHANNEL
        elif event.type == EventType.private_summary:
            channel = whisper_channel_id(event.visible_to)
        else:
            continue
        sender = "Maître du Jeu" if event.author_id is None else name(event.author_id)
        messages.setdefault(channel, []).append({"sender": sender, "content": event.content})
    return messages


def _night_history(memory, human_id) -> list[dict]:
    """Infos de nuit du joueur (rôle, sondages, etc.), pour l'onglet Nuits."""
    return [
        {"turn": e.turn, "text": e.content}
        for e in memory.events_for(human_id)
        if e.type in (EventType.role_info, EventType.night_action)
    ]


def _vote_entry(entry, name) -> dict:
    return {
        "turn": entry["turn"],
        "votes": {
            name(voter): "Personne" if target is None else name(target)
            for voter, target in entry["votes"].items()
        },
        "executed": name(entry["executed"]),
    }