"""Lance une partie dans le même processus que le serveur WebSocket."""
import asyncio
import logging
import random
from typing import Optional

from backend.game_engine import setup_game
from backend.human_port import QueueHumanPort
from backend.human_turns import play_turn_with_human
from backend.server.websockets import register_human

logger = logging.getLogger(__name__)

_current: Optional[asyncio.Task] = None


async def run_game(names: dict[str, str], human_id: str, personality_names: list[str], seed=None):
    rng = random.Random(seed)
    state, agents, memory = setup_game(names, human_id, personality_names, rng)
    port = QueueHumanPort()
    register_human(human_id, port)

    while True:
        result = await play_turn_with_human(state, rng, agents, memory, human_id, port)
        state = result.state
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