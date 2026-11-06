"""Une partie jouée par un humain depuis le navigateur.

GameSession fait le lien entre le moteur (human_turns.play_turn_with_human) et le WebSocket :
elle implémente HumanPort. Chaque fois que le moteur attend l'humain, elle envoie une demande
("request") au navigateur, puis attend l'action correspondante dans sa file `inbox`.

Messages envoyés au navigateur (champ "type") :
- "state"     : tour, phase, joueurs (vivants / morts) et rôle de l'humain ;
- "event"     : un événement de la mémoire visible par l'humain (message public ou privé, annonce, info de nuit) ;
- "request"   : le moteur attend une action de l'humain : kind = "night", "day" (jour minuté : deadline,
                proposal, nominee_options), "private_message", "vote" (pour/contre le joueur désigné)
                ou "final_vote" (fin du jour : qui doit mourir) ;
- "wait"      : le moteur n'attend plus d'action (les IA réfléchissent) ;
- "game_over" : camp gagnant et rôles de tous les joueurs ;
- "error"     : action refusée, ou erreur du serveur.
"""
import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, Optional

from backend.game_engine import setup_game
from backend.human_turns import DAY_SECONDS, MAX_PRIVATE_PARTNERS, DayAction, play_turn_with_human
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
                 max_turns: int = MAX_TURNS, day_seconds: float = DAY_SECONDS):
        self.names = player_names(human_name)
        self.send = send
        self.rng = rng or random.Random()
        self.max_turns = max_turns
        self.inbox: asyncio.Queue = asyncio.Queue()
        self._outbox: asyncio.Queue = asyncio.Queue()
        self.day_seconds = day_seconds
        self.memory = None
        self.state: Optional[GameState] = None  # dernier état connu (route admin)
        self.agents: dict = {}
        self.finished = False
        self._partners: list[str] = []  # agents choisis par l'humain pour le salon privé du jour

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
        self.state = state
        me = state.player(HUMAN_ID)
        self._emit({"type": "state", "data": {
            "turn": state.turn,
            "phase": state.phase.value,
            "players": [self._player_view(state, p.id) for p in state.players],
            "me": {
                "id": me.id,
                "name": me.name,
                "alive": me.alive,
                "can_vote": me.can_vote,  # mort : vrai tant que le vote fantôme n'est pas utilisé
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
                 can_pass: bool = True, state: Optional[GameState] = None,
                 participants: Optional[list[str]] = None) -> None:
        self._emit({"type": "request", "data": {
            "kind": kind,
            "prompt": prompt,
            "options": [{"id": pid, "name": state.player(pid).name} for pid in options] if state else [],
            "count": count,
            "can_pass": can_pass,
            "participants": participants or [],
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

    def _drain(self) -> None:
        """Jette les actions arrivées alors qu'aucune demande n'était ouverte (trop tard)."""
        dropped = 0
        while not self.inbox.empty():
            self.inbox.get_nowait()
            dropped += 1
        if dropped:
            self._error("Action ignorée : elle est arrivée trop tard.")

    def _close_request(self) -> None:
        """Prévient le navigateur que le moteur n'attend plus d'action (les IA réfléchissent)."""
        self._emit({"type": "wait", "data": "Les autres joueurs réfléchissent..."})

    # --- HumanPort ---------------------------------------------------------------------

    async def night_choice(self, state: GameState, player_id: str) -> tuple[str, ...]:
        self._drain()
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

    async def day_action(self, state: GameState, player_id: str, seconds_left: float, wait: float,
                         proposal: Optional[str], nominee_options: list[str]) -> Optional[DayAction]:
        """Le jour, l'humain agit librement : message public, conversation privée, désignation
        ou fin de sa journée. Renvoie None si rien n'arrive pendant `wait` secondes."""
        self._drain()
        self._emit_state(state)
        others = [p.id for p in state.players if p.id != player_id and p.alive]
        self._emit({"type": "request", "data": {
            "kind": "day",
            "prompt": "Discute en public, ouvre une conversation privée, désigne un joueur, "
                      "ou termine ta journée.",
            "options": [{"id": pid, "name": state.player(pid).name} for pid in others],
            "count": MAX_PRIVATE_PARTNERS,
            "can_pass": True,
            "can_nominate": bool(nominee_options),
            "nominee_options": [{"id": pid, "name": state.player(pid).name} for pid in nominee_options],
            "deadline": time.time() + seconds_left,
            "proposal": {"id": proposal, "name": state.player(proposal).name} if proposal else None,
            "participants": [],
        }})
        end = time.monotonic() + wait
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                self._close_request()
                return None
            try:
                action = await asyncio.wait_for(self.inbox.get(), timeout=remaining)
            except asyncio.TimeoutError:
                self._close_request()
                return None

            if action.action == "pass":
                return DayAction("end")
            if action.action == "send_chat":
                if action.payload.channel_id == "public":
                    return DayAction("public", text=action.payload.content)
                self._error("Aucune conversation privée ouverte : écris dans le salon public.")
            elif action.action == "create_channel":
                chosen = tuple(dict.fromkeys(action.payload.target_ids))
                if chosen and all(pid in others for pid in chosen):
                    self._partners = list(chosen)
                    return DayAction("private", targets=chosen, agent_first=(proposal is not None
                                                                              and chosen == (proposal,)))
                self._error("Choix invalide : choisis 1 ou 2 joueurs vivants.")
            elif action.action == "nominate":
                if not nominee_options:
                    self._error("Tu ne peux plus désigner aujourd'hui (un mort ne désigne pas, "
                                "et chacun ne désigne qu'une fois par jour).")
                elif action.payload.target_id in nominee_options:
                    return DayAction("nominate", targets=(action.payload.target_id,))
                else:
                    self._error("Désignation invalide : ce joueur est mort ou a déjà été désigné aujourd'hui.")
            else:
                self._error(f"Action inattendue ({action.action}) pendant le jour.")

    async def private_message(self, state: GameState, player_id: str) -> Optional[str]:
        self._drain()
        while True:
            # Noms des participants : le navigateur ouvre le salon privé tout de suite, avant le premier message.
            participants = sorted(state.player(pid).name for pid in [player_id, *self._partners])
            self._request("private_message", "Écris ton message privé (ou termine la conversation).",
                          participants=participants if self._partners else None)
            action = await self._wait("send_chat")
            if action is None:
                return None
            if action.payload.channel_id == "private":
                return action.payload.content
            self._error("Ce message doit aller dans le salon privé.")

    async def show_private_replies(self, replies: list[tuple[str, str]]) -> None:
        pass  # les réponses arrivent déjà par les événements de la mémoire

    async def vote_on(self, state: GameState, player_id: str, nominee_id: str) -> bool:
        """Vote pour ou contre l'exécution du joueur désigné. « vote » avec target_id = le désigné : pour ;
        target_id = null ou « pass » : contre."""
        self._drain()
        self._emit_state(state)
        nominee = state.player(nominee_id).name
        while True:
            self._request("vote", f"{nominee} a été désigné. Votes-tu pour son exécution ?",
                          [nominee_id], 1, state=state)
            action = await self._wait("vote")
            if action is None or action.payload.target_id is None:
                return False
            if action.payload.target_id == nominee_id:
                return True
            self._error(f"Vote invalide : on vote seulement sur {nominee}.")

    async def final_vote(self, state: GameState, player_id: str) -> Optional[str]:
        """Vote de fin de jour : le joueur qui doit être exécuté, ou personne (target_id null / « pass »)."""
        self._drain()
        self._emit_state(state)
        options = [p.id for p in state.players if p.alive]
        while True:
            self._request("final_vote", "Fin du jour : qui doit être exécuté ? (ou personne)",
                          options, 1, state=state)
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
            self.agents = agents
            self._emit_state(state)
            for event in memory.events_for(HUMAN_ID):  # infos de première nuit déjà enregistrées
                self._on_event(event)
            memory.subscribe(self._on_event)

            winner = None
            for _ in range(self.max_turns):
                result = await play_turn_with_human(state, self.rng, agents, memory, HUMAN_ID, self,
                                                    day_seconds=self.day_seconds)
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
