"""Adaptateur : transforme l'état de la partie au format attendu par le front (static/js).
Il ne calcule aucune règle, il présente ce que le moteur contient déjà.
Le front ne lit que day, phase, aliveCount et players dans l'état ; le reste
(chat, nuits, votes) arrive par des messages dédiés."""
from backend.models import GameState
from backend.models.enums import Phase

# Valeurs attendues par le front (game.js : PHASES, actions.js : kind)
PHASE_FRONT = {
    Phase.NUIT: "nuit",
    Phase.DISCUSSION: "discussion",
    Phase.VOTE: "vote",
}
PUBLIC_CHANNEL = "public"


def whisper_channel_id(member_ids) -> str:
    """Même format que le serveur : whisper_<ids triés>."""
    return "whisper_" + "_".join(sorted(member_ids))


def to_front_state(state: GameState) -> dict:
    """Contenu de game_state.state : ce que game.js et players.js utilisent."""
    return {
        "day": state.turn,
        "phase": PHASE_FRONT[state.phase],
        "aliveCount": len(state.alive_players()),
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "alive": p.alive,
                # Mort : le front affiche « vote dispo » ou « vote utilisé »
                "has_vote": p.can_vote,
            }
            for p in state.players
        ],
    }