"""Lien entre le serveur WebSocket et la partie en cours.

Le moteur pose ses demandes dans port.requests (vote, action de nuit, etc.).
La boucle _pump les transmet au joueur et retient la demande en attente.
Une réponse n'est acceptée que si elle correspond à la demande attendue :
un message tardif ne peut pas être pris pour la réponse à une autre question."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.front_state import to_front_state
from backend.human_port import QueueHumanPort
from backend.memory_manager import MemoryManager
from backend.models import GameState
from backend.server.connection_manager import manager

logger = logging.getLogger(__name__)

PUBLIC_CHANNEL = "public"

# Demandes auxquelles le joueur peut répondre depuis le front.
ANSWERABLE = {"night_choice", "vote", "public_message", "private_partners", "private_message"}
REQUEST_TO_MESSAGE = {"night_choice": "night_request", "vote": "vote_request"}


@dataclass
class GameSession:
    human_id: str
    port: QueueHumanPort
    memory: MemoryManager
    state: Optional[GameState] = None  # mis à jour par la boucle de jeu
    votes_history: list[dict] = field(default_factory=list)
    pending: Optional[str] = None  # demande en attente de réponse
    choices: Optional[list[str]] = None  # choix proposés (private_partners)
    whisper_members: Optional[frozenset[str]] = None  # salon privé ouvert
    pump_task: Optional[asyncio.Task] = None


class GameRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}

    def add(self, session: GameSession) -> None:
        """À appeler depuis une coroutine (create_task exige une boucle en cours)."""
        self._sessions[session.human_id] = session
        session.pump_task = asyncio.create_task(_pump(session))

    def get(self, player_id: str) -> Optional[GameSession]:
        return self._sessions.get(player_id)

    def remove(self, player_id: str) -> None:
        session = self._sessions.pop(player_id, None)
        if session and session.pump_task:
            session.pump_task.cancel()


games = GameRegistry()


def answer(session: GameSession, kind: str, value: Any) -> bool:
    """Transmet la réponse au moteur si c'est bien la demande attendue. Renvoie False sinon."""
    if session.pending != kind:
        return False
    session.pending = None
    session.choices = None
    session.port.answers.put_nowait(value)
    return True


async def push_state(session: GameSession) -> None:
    """Envoie au front l'état de la partie vu par le joueur."""
    if session.state is None:
        return
    view = to_front_state(
        session.state, session.memory, session.human_id, tuple(session.votes_history)
    )
    await manager.send_to_player(session.human_id, {"type": "state_update", "data": view})


async def _pump(session: GameSession) -> None:
    """Lit les demandes du moteur, les transmet au joueur et retient la demande attendue."""
    while True:
        try:
            request = await session.port.requests.get()
            kind = request["kind"]
            payload = {k: v for k, v in request.items() if k != "kind"}
            session.pending = kind if kind in ANSWERABLE else None
            session.choices = payload.get("choices")
            msg_type = REQUEST_TO_MESSAGE.get(kind, "engine_request")
            await manager.send_to_player(
                session.human_id, {"type": msg_type, "kind": kind, "data": payload}
            )
            await push_state(session)
        except Exception:
            logger.exception("Erreur dans la boucle de demandes de %s", session.human_id)