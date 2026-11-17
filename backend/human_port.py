import asyncio
from typing import Optional

from backend.models import GameState
from backend.rules import legal_actions


class QueueHumanPort:
    """Implémentation de HumanPort pilotée par des files.
    Le moteur pose une demande dans `requests`, puis attend la réponse dans `answers`.
    Le serveur lit `requests` pour prévenir le joueur, et met les réponses dans `answers`.
    Chaque demande transmet l'état courant : le serveur s'en sert pour l'affichage du front."""

    def __init__(self) -> None:
        self.requests: asyncio.Queue = asyncio.Queue()
        self.answers: asyncio.Queue = asyncio.Queue()
        # Renseignés par game_runner et mis à jour à chaque demande : le serveur s'en sert pour le front.
        self.state: Optional[GameState] = None
        self.memory = None
        self.votes_history: list[dict] = []

    async def _ask(self, kind: str, **payload):
        await self.requests.put({"kind": kind, **payload})
        return await self.answers.get()

    async def _tell(self, kind: str, **payload) -> None:
        await self.requests.put({"kind": kind, **payload})

    async def night_choice(self, state: GameState, player_id: str) -> tuple[str, ...]:
        self.state = state
        legal = legal_actions(state, player_id)
        return tuple(await self._ask("night_choice", targets=list(legal.targets), count=legal.count))

    async def show_night_info(self, state: GameState, turn: int, info: str, allies: Optional[list[dict]]) -> None:
        self.state = state
        await self._tell("night_info", turn=turn, info=info, allies=allies)

    async def show_night_deaths(self, state: GameState, deaths: tuple[str, ...]) -> None:
        self.state = state
        await self._tell("night_deaths", deaths=list(deaths))

    async def show_public_message(self, state: GameState, author: str, text: str) -> None:
        self.state = state
        await self._tell("public_chat", author=author, text=text)

    async def public_message(self, state: GameState, player_id: str) -> Optional[str]:
        self.state = state
        return await self._ask("public_message")

    async def private_partners(self, state: GameState, player_id: str) -> list[str]:
        self.state = state
        alive = [p.id for p in state.alive_players() if p.id != player_id]
        return await self._ask("private_partners", choices=alive)

    async def private_message(self, state: GameState, player_id: str) -> Optional[str]:
        self.state = state
        return await self._ask("private_message")

    async def show_private_replies(self, state: GameState, replies: list[tuple[str, str]]) -> None:
        self.state = state
        await self._tell("private_replies", replies=[{"author": pid, "text": text} for pid, text in replies])

    async def vote(self, state: GameState, player_id: str) -> Optional[str]:
        self.state = state
        targets = [p.id for p in state.alive_players()]
        return await self._ask("vote", targets=targets)