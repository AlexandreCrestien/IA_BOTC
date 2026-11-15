"""Lance la partie dans le même processus que le serveur, à la première connexion du joueur humain."""
import asyncio
import logging
import random
from typing import Optional

from backend.game_engine import setup_game
from backend.human_port import QueueHumanPort
from backend.human_turns import play_turn_with_human
from backend.server.websockets import register_human

logger = logging.getLogger(__name__)

# Configuration de la partie
GAME_CONFIG = {
    "names": {
        "Sasha": "Sasha",
        "p1": "marIA",
        "p2": "tobIAs",
        "p3": "mAIsie",
        "p4": "adrIAn",
        "p5": "dIAne",
    },
    "human_id": "Sasha",
    "personality_names": ["agitator", "clown", "observer", "paranoid", "strategist"],
}

_current: Optional[asyncio.Task] = None


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
        if result.game_winner is not None:
            logger.info("Partie terminée, vainqueur : %s", result.game_winner)
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


def ensure_started(player_id: str) -> None:
    """Lance la partie une seule fois, quand le joueur humain se connecte."""
    if player_id != GAME_CONFIG["human_id"] or _current is not None:
        return
    start_game(**GAME_CONFIG)