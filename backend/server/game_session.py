"""Une partie jouée par un humain depuis le navigateur.

GameSession fait le lien entre le moteur (human_turns.play_turn_with_human) et le WebSocket :
elle implémente HumanPort. Chaque fois que le moteur attend l'humain, elle envoie une demande
("request") au navigateur, puis attend l'action correspondante dans sa file `inbox`.

Messages envoyés au navigateur (champ "type") :
- "state"     : tour, phase, joueurs (vivants / morts) et rôle de l'humain ;
- "event"     : un événement de la mémoire visible par l'humain (message public ou privé, annonce, info de nuit) ;
- "request"   : le moteur attend une action de l'humain (kind, prompt, options, count, can_pass) ;
- "game_over" : camp gagnant et rôles de tous les joueurs ;
- "error"     : action refusée, ou erreur du serveur.
"""
import asyncio
import logging
import random
from typing import Any, Awaitable, Callable, Optional

from backend.game_engine import setup_game
from backend.human_turns import play_turn_with_human
from backend.memory_manager import Event
from backend.models import Alignement, GameState
from backend.rules import legal_actions

logger = logging.getLogger(__name__)

HUMAN_ID = "humain"
AI_NAMES = ["marIA", "tobIAs", "mAIsie", "adrIAn", "dIAne"]
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]
MAX_TURNS = 10

TEAM_LABELS = {"villageois": "Villageois", "outsider": "Outsider", "sbire": "Sbire", "demon": "Démon"}
WINNER_LABELS = {Alignement.BON: "Le bien (villageois)", Alignement.MAUVAIS: "Le mal (démon et sbire)"}

Send = Callable[[dict[str, Any]], Awaitable[None]]


def player_names(human_name: str) -> dict[str, str]:
    """{id: nom} des 6 joueurs. Le nom de l'humain ne doit pas être celui d'une IA."""
    name = human_name.strip() or "Joueur"
    if name in AI_NAMES:
        name = f"{name} (humain)"
    names = {HUMAN_ID: name}
    names.update({f"ia{i}": ai_name for i, ai_name in enumerate(AI_NAMES, 1)})
    return names


class GameSession:
    def __init__(self, human_name: str, send: Send, rng: Optional[random.Random] = None,
                 max_turns: int = MAX_TURNS):
        self.names = player_names(human_name)
        self.send = send
        self.rng = rng or random.Random()
        self.max_turns = max_turns
        self.inbox: asyncio.Queue = asyncio.Queue()
        self._outbox: asyncio.Queue = asyncio.Queue()
        self.memory = None
        self.finished = False

    # --- Envoi vers le navigateur (toujours dans l'ordre) ---------------------------

    def _emit(self, message: dict[str, Any]) -> None:
        self._outbox.put_nowait(message)

    async def _sender(self) -> None:
        while True:
            message = await self._outbox.get()
            try:
                await self.send(message)
            finally:
                self._outbox.task_done()

    def _player_view(self, state: GameState, player_id: str) -> dict[str, Any]:
        player = state.player(player_id)
        return {"id": player.id, "name": player.name, "alive": player.alive,
                "can_vote": player.can_vote, "is_me": player.id == HUMAN_ID}

    def _emit_state(self, state: GameState) -> None:
        me = state.player(HUMAN_ID)
        self._emit({"type": "state", "data": {
            "turn": state.turn,
            "phase": state.phase.value,
            "players": [self._player_view(state, p.id) for p in state.players],
            "me": {
                "id": me.id,
                "name": me.name,
                "alive": me.alive,
                "role": me.role.name_FR,
                "description": me.role.description,
                "team": TEAM_LABELS.get(me.role.team.value, me.role.team.value),
                "alignment": "bien" if me.role.alignment == Alignement.BON else "mal",
            },
        }})

    def _on_event(self, event: Event) -> None:
        """Appelé par la mémoire à chaque événement : on transmet ceux que l'humain peut voir."""
        if event.visible_to is not None and HUMAN_ID not in event.visible_to:
            return
        if event.visible_to is None:
            channel = "public"
        elif event.visible_to == {HUMAN_ID}:
            channel = "personal"
        else:
            channel = "private"
        if event.author_id is None:
            author = "Maître du Jeu"
        else:
            author = self.memory.name_of(event.author_id)
        participants = sorted(self.memory.name_of(p) for p in (event.visible_to or ()))
        self._emit({"type": "event", "data": {
            "kind": event.type.value,
            "channel": channel,
            "author": author,
            "is_me": event.author_id == HUMAN_ID,
            "is_game_master": event.author_id is None,
            "content": event.content,
            "turn": event.turn,
            "phase": event.phase.value,
            "participants": participants,
        }})

    # --- Attente des actions de l'humain ---------------------------------------------

    def _request(self, kind: str, prompt: str, options: list[str] = (), count: int = 0,
                 can_pass: bool = True, state: Optional[GameState] = None) -> None:
        self._emit({"type": "request", "data": {
            "kind": kind,
            "prompt": prompt,
            "options": [{"id": pid, "name": state.player(pid).name} for pid in options] if state else [],
            "count": count,
            "can_pass": can_pass,
        }})

    async def _wait(self, expected: str):
        """Attend une action du type attendu, ou "pass" (renvoie None). Les autres sont refusées."""
        while True:
            action = await self.inbox.get()
            if action.action == "pass":
                return None
            if action.action == expected:
                return action
            self._emit({"type": "error", "data": f"Action inattendue ({action.action}) : on attend {expected}."})

    def _error(self, text: str) -> None:
        self._emit({"type": "error", "data": text})

    # --- HumanPort ---------------------------------------------------------------------

    async def night_choice(self, state: GameState, player_id: str) -> tuple[str, ...]:
        self._emit_state(state)
        legal = legal_actions(state, player_id)
        role = state.player(player_id).role
        prompt = f"{role.name_FR} : {role.description} Choisis {legal.count} joueur(s)."
        while True:
            self._request("night", prompt, list(legal.targets), legal.count, state=state)
            action = await self._wait("night_action")
            if action is None:
                return ()  # le moteur fera un choix légal au hasard
            targets = tuple(action.payload.targets)
            if len(targets) == legal.count and len(set(targets)) == len(targets) \
                    and all(t in legal.targets for t in targets):
                return targets
            self._error(f"Choix invalide : il faut {legal.count} joueur(s) parmi les options.")

    async def show_night_deaths(self, state: GameState, deaths: tuple[str, ...]) -> None:
        self._emit_state(state)

    async def public_message(self, state: GameState, player_id: str) -> Optional[str]:
        self._emit_state(state)
        while True:
            self._request("public_message", "À toi de parler dans le salon public (ou passe ton tour).")
            action = await self._wait("send_chat")
            if action is None:
                return None
            if action.payload.channel_id == "public":
                return action.payload.content
            self._error("Ce message doit aller dans le salon public.")

    async def private_partners(self, state: GameState, player_id: str) -> list[str]:
        options = [p.id for p in state.players if p.id != player_id and p.alive]
        while True:
            self._request("private_partners",
                          "Choisis 1 ou 2 joueurs pour une conversation privée. "
                          "Si tu passes, un joueur viendra peut-être te parler.",
                          options, 2, state=state)
            action = await self._wait("create_channel")
            if action is None:
                return []
            chosen = list(dict.fromkeys(action.payload.target_ids))
            if all(pid in options for pid in chosen):
                return chosen
            self._error("Choix invalide : choisis des joueurs vivants.")

    async def private_message(self, state: GameState, player_id: str) -> Optional[str]:
        while True:
            self._request("private_message", "Écris ton message privé (ou termine la conversation).")
            action = await self._wait("send_chat")
            if action is None:
                return None
            if action.payload.channel_id == "private":
                return action.payload.content
            self._error("Ce message doit aller dans le salon privé.")

    async def show_private_replies(self, replies: list[tuple[str, str]]) -> None:
        pass  # les réponses arrivent déjà par les événements de la mémoire

    async def vote(self, state: GameState, player_id: str) -> Optional[str]:
        self._emit_state(state)
        options = [p.id for p in state.players if p.alive]
        while True:
            self._request("vote", "Vote pour exécuter un joueur, ou vote pour personne.", options, 1, state=state)
            action = await self._wait("vote")
            if action is None or action.payload.target_id is None:
                return None
            if action.payload.target_id in options:
                return action.payload.target_id
            self._error("Vote invalide : choisis un joueur vivant.")

    # --- Partie ----------------------------------------------------------------------------

    def _emit_game_over(self, state: GameState, winner: Optional[Alignement]) -> None:
        self._emit({"type": "game_over", "data": {
            "winner": WINNER_LABELS.get(winner, "Personne : partie arrêtée"),
            "human_won": winner is not None and state.player(HUMAN_ID).role.alignment == winner,
            "roles": [{"name": p.name, "role": p.role.name_FR, "alive": p.alive, "is_me": p.id == HUMAN_ID}
                      for p in state.players],
        }})

    async def run(self) -> None:
        sender = asyncio.create_task(self._sender())
        try:
            state, agents, memory = setup_game(self.names, HUMAN_ID, PERSONALITIES, self.rng)
            self.memory = memory
            self._emit_state(state)
            for event in memory.events_for(HUMAN_ID):  # infos de première nuit déjà enregistrées
                self._on_event(event)
            memory.subscribe(self._on_event)

            winner = None
            for _ in range(self.max_turns):
                result = await play_turn_with_human(state, self.rng, agents, memory, HUMAN_ID, self)
                state = result.state
                self._emit_state(state)
                if result.game_winner is not None:
                    winner = result.game_winner
                    break
            self._emit_game_over(state, winner)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("La partie s'est arrêtée sur une erreur")
            self._error("Erreur du serveur : la partie est arrêtée. Relance une partie.")
        finally:
            self.finished = True
            try:
                await asyncio.wait_for(self._outbox.join(), timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            sender.cancel()
