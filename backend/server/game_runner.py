"""Lance la partie dans le même processus que le serveur, à la première connexion du joueur humain."""
import asyncio
import logging
import random
from typing import Optional

from backend.game_engine import setup_game
from backend.human_port import QueueHumanPort
from backend.human_turns import play_turn_with_human
from backend.models import Alignement
from backend.server.websockets import register_human, send_game_over, send_vote_result

logger = logging.getLogger(__name__)

# Noms des 5 agents IA (identifiant -> nom affiché)
AI_NAMES = {
    "p1": "marIA",
    "p2": "tobIAs",
    "p3": "mAIsie",
    "p4": "adrIAn",
    "p5": "dIAne",
}

# Configuration de la partie. Le joueur humain prend le pseudo qu'il choisit à la connexion.
GAME_CONFIG = {
    "personality_names": ["agitator", "clown", "observer", "paranoid", "strategist"],
    "seed": None,  # tests : fixer une graine pour rejouer la même partie
}

# Libellés affichés par le front (il reconnaît le camp du joueur au mot « Démon »)
WINNER_LABELS = {
    Alignement.BON: "Villageois",
    Alignement.MAUVAIS: "Démons",
}

_current: Optional[asyncio.Task] = None


def _winner_label(winner) -> str:
    return WINNER_LABELS.get(winner, str(winner))


def _all_players(state):
    players = state.players
    return players.values() if isinstance(players, dict) else players


async def run_game(names: dict[str, str], human_id: str, personality_names: list[str], seed=None):
    rng = random.Random(seed)
    state, agents, memory = setup_game(names, human_id, personality_names, rng)
    port = QueueHumanPort()
    port.memory = memory
    port.state = state
    register_human(human_id, port)

    while True:
        turn = state.turn
        result = await play_turn_with_human(state, rng, agents, memory, human_id, port)
        state = result.state
        port.state = state
        port.votes_history.append({"turn": turn, "votes": result.votes, "executed": result.executed})

        # Le front reçoit des noms, jamais des identifiants internes
        label = {p.id: p.name for p in _all_players(state)}
        votes = [
            {"voter": label.get(voter, voter), "target": label.get(target, target) if target else None}
            for voter, target in result.votes.items()
        ]
        executed = label.get(result.executed, result.executed) if result.executed else None
        await send_vote_result(human_id, turn, executed, votes)

        if result.game_winner is not None:
            logger.info("Partie terminée, vainqueur : %s", result.game_winner)
            await send_game_over(
                human_id,
                _winner_label(result.game_winner),
                "Le village a rendu son dernier verdict.",
            )
            return state


def _log_end(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error("Partie interrompue", exc_info=error)


def start_game(names, human_id, personality_names, seed=None) -> asyncio.Task:
    """Lance la partie si aucune n'est en cours. Doit être appelée depuis une coroutine."""
    global _current
    if _current is not None and not _current.done():
        return _current
    _current = asyncio.create_task(run_game(names, human_id, personality_names, seed))
    _current.add_done_callback(_log_end)
    return _current


def _pseudo_is_valid(pseudo: str) -> bool:
    """Refuse un pseudo vide, réservé, ou déjà pris par un agent (sans tenir compte de la casse)."""
    taken = {k.casefold() for k in AI_NAMES} | {v.casefold() for v in AI_NAMES.values()} | {"game_master"}
    return pseudo.strip() != "" and pseudo.casefold() not in taken


def ensure_started(player_id: str) -> None:
    """Lance la partie au premier joueur humain qui se connecte, avec son pseudo comme nom."""
    if _current is not None:
        return
    if not _pseudo_is_valid(player_id):
        logger.warning("Pseudo refusé pour la partie : %r", player_id)
        return
    names = {player_id: player_id, **AI_NAMES}
    start_game(names, player_id, GAME_CONFIG["personality_names"], GAME_CONFIG["seed"])