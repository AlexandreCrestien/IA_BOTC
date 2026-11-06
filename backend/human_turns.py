"""Tour complet avec l'humain et les IA.

Nuit : les IA puis l'humain font leur choix ; les morts sont annoncés le matin.
Jour (minuté, DAY_SECONDS) : les IA ouvrent la discussion publique, puis l'humain agit librement
jusqu'à la fin du temps :
- message public (les IA lui répondent) ;
- conversation privée avec 1 ou 2 agents (3 messages au plus) ; pendant ce temps, les autres agents
  discutent entre eux (conversation simulée en un seul appel LLM) ;
- désignation d'un joueur (facultative) : vote immédiat pour ou contre son exécution ;
- fin de sa journée.
À la moitié du temps, les IA peuvent désigner à leur tour, et si l'humain n'a parlé en privé
avec personne, un agent lui propose une conversation.
Chaque joueur désigne au plus une fois par jour et n'est désigné qu'une fois par jour.
Si une désignation mène à une exécution, le jour s'arrête. Sinon, le jour continue.
Vote de fin de jour : si personne n'a été exécuté, chacun choisit qui doit mourir (ou personne).

Chaque étape attend la précédente : l'humain n'écrit jamais pendant un appel IA.
Un joueur mort peut encore parler et voter (vote fantôme), mais ne peut pas désigner.
"""
import asyncio
import random
import time
from typing import Callable, NamedTuple, Optional, Protocol

from backend.ai_turns import collect_ai_nomination, collect_ai_night_choices, final_vote, vote_on_nomination
from backend.conversations import (choose_agent_for_human, private_message, public_conversation,
                                   simulate_agents_conversation, start_private_conversation)
from backend.game_engine import TurnResult, _deaths, announce_night, play_night, reveal_psychic_answer
from backend.memory_manager import MemoryManager
from backend.models import EventType, GameState, Phase
from backend.rules import night_steps, winner

DAY_SECONDS = 240
MAX_HUMAN_PRIVATE_MESSAGES = 3
MAX_PRIVATE_PARTNERS = 2
PUBLIC_REPLIES = 3  # messages des IA après chaque message public de l'humain


class DayAction(NamedTuple):
    """Action de l'humain pendant le jour.
    kind : "public" (text), "private" (targets, agent_first), "nominate" (targets[0]) ou "end"."""
    kind: str
    text: Optional[str] = None
    targets: tuple[str, ...] = ()
    agent_first: bool = False


class HumanPort(Protocol):
    """Interface entre le moteur et l'humain. Chaque méthode attend la réponse de l'humain."""

    async def night_choice(self, state: GameState, player_id: str) -> tuple[str, ...]: ...
    async def show_night_deaths(self, state: GameState, deaths: tuple[str, ...]) -> None: ...

    async def day_action(self, state: GameState, player_id: str, seconds_left: float, wait: float,
                         proposal: Optional[str], nominee_options: list[str]) -> Optional[DayAction]:
        """Attend une action du jour pendant `wait` secondes au plus (None si rien n'arrive).
        proposal : id d'un agent qui propose une conversation privée (l'humain l'accepte
        avec DayAction("private", targets=(proposal,), agent_first=True)).
        nominee_options : joueurs que l'humain peut désigner (vide s'il ne peut pas désigner)."""
        ...

    async def private_message(self, state: GameState, player_id: str) -> Optional[str]: ...
    async def show_private_replies(self, replies: list[tuple[str, str]]) -> None: ...
    async def vote_on(self, state: GameState, player_id: str, nominee_id: str) -> bool: ...
    async def final_vote(self, state: GameState, player_id: str) -> Optional[str]: ...


def _human_must_choose(state: GameState, player_id: str) -> bool:
    return any(pid == player_id and needs for pid, needs in night_steps(state))


async def _private_channel(
    state: GameState,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
    partner_ids: tuple[str, ...],
    agent_first: bool,
) -> bool:
    """Conversation privée de l'humain avec 1 ou 2 agents vivants (MAX_HUMAN_PRIVATE_MESSAGES messages
    au plus). En parallèle, les autres agents ont leur propre conversation, simulée en un appel.
    Renvoie False si aucun partenaire valide."""
    partners = [agents[pid] for pid in dict.fromkeys(partner_ids)
                if pid in agents and state.player(pid).alive][:MAX_PRIVATE_PARTNERS]
    if not partners:
        return False

    chosen = {agent.player_id for agent in partners}
    others = [agents[p.id] for p in state.players if p.id in agents and p.id not in chosen]
    parallel = asyncio.create_task(simulate_agents_conversation(others, memory)) if len(others) >= 2 else None

    replies = await start_private_conversation(human_id, partners, memory, agent_speaks_first=agent_first)
    if replies:
        await human.show_private_replies(replies)
    for _ in range(MAX_HUMAN_PRIVATE_MESSAGES):
        text = await human.private_message(state, human_id)
        if not text:
            break
        replies = await private_message(human_id, text, partners, memory)
        await human.show_private_replies(replies)

    if parallel is not None:
        await parallel
    return True


async def play_day_with_human(
    state: GameState,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
    day_seconds: float = DAY_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[GameState, dict[str, Optional[str]], Optional[str]]:
    """Jour minuté (state en phase DISCUSSION). Les désignations sont votées tout de suite.
    Renvoie (état, votes, exécuté) : exécuté = None si aucune désignation n'a abouti
    (le vote de fin de jour est alors fait par play_turn_with_human)."""
    start = clock()
    deadline = start + day_seconds
    half = start + day_seconds / 2
    speakers = [agents[p.id] for p in state.players if p.id in agents]

    nominators: set[str] = set()
    nominees: set[str] = set()
    votes: dict[str, Optional[str]] = {}

    async def human_ballot(vote_state: GameState, nominee_id: str) -> dict[str, bool]:
        if not vote_state.player(human_id).can_vote:
            return {}
        return {human_id: await human.vote_on(vote_state, human_id, nominee_id)}

    async def nominate(nomination: tuple[str, str]):
        """Vote immédiat sur une désignation. Renvoie (état, votes, exécuté)."""
        nominators.add(nomination[0])
        nominees.add(nomination[1])
        return await vote_on_nomination(state, agents, memory, nomination,
                                        lambda s: human_ballot(s, nomination[1]))

    async def ask_agents():
        return await collect_ai_nomination(state, agents, frozenset(nominators), frozenset(nominees))

    await public_conversation(speakers, memory)

    agents_asked = False
    had_private = False
    proposal: Optional[str] = None
    proposal_made = False

    while True:
        now = clock()
        if now >= deadline:
            return state, votes, None

        if now >= half and not agents_asked:
            agents_asked = True
            nomination = await ask_agents()
            if nomination is not None:
                state, votes, executed = await nominate(nomination)
                if executed is not None:
                    return state, votes, executed
                continue

        if now >= half and not had_private and not proposal_made:
            proposal_made = True
            alive_agents = [agents[p.id] for p in state.players if p.id in agents and p.alive]
            if alive_agents:
                proposal = choose_agent_for_human(alive_agents, human_id, memory).player_id

        can_nominate = state.player(human_id).alive and human_id not in nominators
        nominee_options = [p.id for p in state.players
                           if can_nominate and p.alive and p.id != human_id and p.id not in nominees]
        next_check = deadline if agents_asked else half
        action = await human.day_action(state, human_id, max(deadline - clock(), 0),
                                        max(next_check - clock(), 0), proposal, nominee_options)
        if action is None:
            continue

        if action.kind == "public" and action.text:
            memory.add_public(EventType.public_message, human_id, action.text)
            await public_conversation(speakers, memory, max_messages=PUBLIC_REPLIES)
        elif action.kind == "private":
            if await _private_channel(state, agents, memory, human_id, human, action.targets, action.agent_first):
                had_private = True
                proposal = None
        elif action.kind == "nominate" and action.targets and action.targets[0] in nominee_options:
            state, votes, executed = await nominate((human_id, action.targets[0]))
            if executed is not None:
                return state, votes, executed
        elif action.kind == "end":
            if not agents_asked:
                agents_asked = True
                nomination = await ask_agents()
                if nomination is not None:
                    state, votes, executed = await nominate(nomination)
                    if executed is not None:
                        return state, votes, executed
            return state, votes, None


async def play_turn_with_human(
    state: GameState,
    rng: random.Random,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
    day_seconds: float = DAY_SECONDS,
) -> TurnResult:
    """Tour complet avec un humain et les IA : nuit, jour minuté, vote éventuel."""
    if state.phase != Phase.NUIT:
        raise ValueError("un tour commence par la nuit")

    # NUIT : IA en parallèle, puis l'humain
    memory.set_moment(state.turn, state.phase)
    ai_night = await collect_ai_night_choices(state, agents)
    human_night: dict[str, tuple[str, ...]] = {}
    if _human_must_choose(state, human_id):
        human_night[human_id] = await human.night_choice(state, human_id)
    night_answers = {**ai_night, **human_night}
    after_night, night_choices = play_night(state, rng, lambda s, pid: night_answers.get(pid, ()))
    reveal_psychic_answer(after_night, night_choices, memory, rng)

    night_deaths = _deaths(state, after_night)
    memory.set_moment(after_night.turn, Phase.DISCUSSION)  # l'annonce du matin est datée du jour
    announce_night(memory, after_night, night_deaths)
    await human.show_night_deaths(after_night, night_deaths)
    if winner(after_night) is not None:
        return TurnResult(after_night, night_choices, {}, None, night_deaths, winner(after_night))

    # JOUR minuté : discussion, conversations privées, désignation
    discussion = after_night.next_phase()
    memory.set_moment(discussion.turn, discussion.phase)
    discussion, votes, executed = await play_day_with_human(discussion, agents, memory, human_id, human,
                                                            day_seconds)

    # VOTE de fin de jour, si personne n'a été exécuté sur désignation (l'humain vote aussi,
    # par vote fantôme s'il est mort)
    day_state = discussion.next_phase()
    memory.set_moment(day_state.turn, day_state.phase)
    if executed is None:
        async def human_vote(vote_state: GameState) -> dict[str, Optional[str]]:
            if not vote_state.player(human_id).can_vote:
                return {}
            return {human_id: await human.final_vote(vote_state, human_id)}

        after_day, votes, executed = await final_vote(day_state, agents, memory, human_vote)
    else:
        after_day = day_state
    game_winner = winner(after_day)
    if game_winner is None:
        after_day = after_day.next_phase()
    return TurnResult(after_day, night_choices, votes, executed, night_deaths, game_winner)
