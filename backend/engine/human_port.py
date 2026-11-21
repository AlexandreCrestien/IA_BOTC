import asyncio
from typing import Optional

from backend.models import GameState
from backend.rules import legal_actions, vote_targets


class AutoHumanPort:
    """Joueur sans agent qui ne parle jamais : parties « IA seules » (scripts, tests).
    Choix de nuit laissé au moteur (choix légal au hasard), pas de message, pas de salon privé,
    refuse les entretiens et s'abstient au vote."""

    async def night_choice(self, state: GameState, player_id: str) -> tuple[str, ...]:
        return ()  # le moteur remplace un choix vide par un choix légal au hasard

    async def show_night_info(self, state, turn, info, allies) -> None: ...
    async def show_night_deaths(self, state, deaths) -> None: ...
    async def show_public_message(self, state, author, text) -> None: ...
    async def show_private_replies(self, state, replies) -> None: ...
    async def show_agent_meeting(self, state, agent_ids) -> None: ...

    async def public_message(self, state: GameState, player_id: str) -> Optional[str]:
        return None

    async def private_partners(self, state: GameState, player_id: str) -> Optional[list[str]]:
        return []

    async def agent_invitation(self, state: GameState, player_id: str, agent_id: str) -> bool:
        return False

    async def private_message(self, state: GameState, player_id: str) -> Optional[str]:
        return None

    async def vote(self, state: GameState, player_id: str) -> Optional[str]:
        return None

    async def show_agent_unavailable(self, state, agent_id, step) -> None: ...


class QueueHumanPort:
    """Implémentation de HumanPort pilotée par des files.
    Le moteur pose une demande dans `requests`, puis attend la réponse dans `answers`.
    Le serveur lit `requests` pour prévenir le joueur, et met les réponses dans `answers`.
    Chaque demande contient l'état courant (clé "state") : le serveur s'en sert pour l'affichage du front."""

    def __init__(self) -> None:
        self.requests: asyncio.Queue = asyncio.Queue()
        self.answers: asyncio.Queue = asyncio.Queue()

    async def _ask(self, kind: str, state: GameState, **payload):
        await self.requests.put({"kind": kind, "state": state, **payload})
        return await self.answers.get()

    async def _tell(self, kind: str, state: GameState, **payload) -> None:
        await self.requests.put({"kind": kind, "state": state, **payload})

    async def night_choice(self, state: GameState, player_id: str) -> tuple[str, ...]:
        legal = legal_actions(state, player_id)
        return tuple(await self._ask("night_choice", state, targets=list(legal.targets), count=legal.count))

    async def show_night_info(self, state: GameState, turn: int, info: str, allies: Optional[list[dict]]) -> None:
        await self._tell("night_info", state, turn=turn, info=info, allies=allies)

    async def show_night_deaths(self, state: GameState, deaths: tuple[str, ...]) -> None:
        await self._tell("night_deaths", state, deaths=list(deaths))

    async def show_public_message(self, state: GameState, author: str, text: str) -> None:
        await self._tell("public_chat", state, author=author, text=text)

    async def public_message(self, state: GameState, player_id: str) -> Optional[str]:
        return await self._ask("public_message", state)

    async def private_partners(self, state: GameState, player_id: str) -> Optional[list[str]]:
        """[] : pas de salon privé. None : le joueur n'a rien décidé à temps (un agent viendra le voir)."""
        # Morts compris : un joueur mort peut encore parler
        others = [p.id for p in state.players if p.id != player_id]
        return await self._ask("private_partners", state, choices=others)

    async def agent_invitation(self, state: GameState, player_id: str, agent_id: str) -> bool:
        """Un agent propose un entretien au joueur. True s'il accepte."""
        return bool(await self._ask("agent_invitation", state, agent=agent_id))

    async def private_message(self, state: GameState, player_id: str) -> Optional[str]:
        return await self._ask("private_message", state)

    async def show_private_replies(self, state: GameState, replies: list[tuple[str, str]]) -> None:
        await self._tell("private_replies", state, replies=[{"author": pid, "text": text} for pid, text in replies])

    async def show_agent_meeting(self, state: GameState, agent_ids: tuple[str, str]) -> None:
        """Deux agents s'entretiennent en privé : annonce publique (un indice pour le joueur)."""
        await self._tell("agent_meeting", state, agents=list(agent_ids))

    async def vote(self, state: GameState, player_id: str) -> Optional[str]:
        return await self._ask("vote", state, targets=vote_targets(state, player_id))

    async def show_turn_result(self, state: GameState, turn: int, votes: list[dict], executed: Optional[str]) -> None:
        """Fin du tour : bulletins (ids, voix d'outre-tombe signalées) et exécution. Posé par game_runner."""
        await self._tell("vote_result", state, turn=turn, votes=votes, executed=executed)

    async def show_agent_unavailable(self, state: GameState, agent_id: str, step: str) -> None:
        """L'IA d'un agent n'a pas répondu (step : night, public, private, vote). Le serveur décide quoi montrer."""
        await self._tell("agent_unavailable", state, agent=agent_id, step=step)

    async def show_game_over(self, state: GameState, winner: str, details: str) -> None:
        """Fin de partie : winner = "good" | "evil". Posé par game_runner."""
        await self._tell("game_over", state, winner=winner, details=details)
