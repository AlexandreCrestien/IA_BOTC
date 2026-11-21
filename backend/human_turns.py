"""Tour complet avec l'humain et les IA.
Ordre : nuit (IA puis humain), infos de nuit de l'humain, morts de la nuit affichées,
discussion publique des IA, message public de l'humain, salon privé facultatif
(3 messages max, 1 ou 2 IA répondant en parallèle), vote (IA puis humain).
Si l'humain ne décide rien pour le salon privé, un agent vient lui proposer un entretien.
Pendant le salon privé de l'humain, deux autres agents s'entretiennent en privé (conversation simulée).
Chaque étape attend la précédente : l'humain n'écrit jamais pendant un appel IA.
Un joueur mort peut encore parler et voter."""
import asyncio
import logging
import random
from typing import Optional, Protocol

from backend.agent_whispers import choose_whisper_pair, write_whisper_summaries
from backend.ai_turns import collect_ai_night_choices, collect_ai_votes
from backend.conversations import choose_agent_for_human, public_conversation, start_private_conversation
from backend.game_engine import (
    TurnResult,
    _deaths,
    play_day,
    play_night,
    record_night_choices,
    record_night_deaths,
    record_vote,
    reveal_psychic_answer,
)
from backend.memory_manager import MemoryManager
from backend.models import Equipe, EventType, GameState, Phase
from backend.rules import night_steps, winner

logger = logging.getLogger(__name__)

MAX_HUMAN_PRIVATE_MESSAGES = 3
MAX_PRIVATE_PARTNERS = 2


class HumanPort(Protocol):
    """Interface entre le moteur et l'humain. Chaque méthode attend la réponse de l'humain.
    None signifie « rien » : pas de message, pas de salon privé, abstention.
    Les méthodes show_* transmettent l'état courant, pour que le front affiche la bonne phase.
    private_partners : [] si l'humain ne veut pas de salon privé, None s'il n'a rien décidé à temps
    (un agent vient alors lui proposer un entretien, voir agent_invitation)."""

    async def night_choice(self, state: GameState, player_id: str) -> tuple[str, ...]: ...
    async def show_night_info(self, state: GameState, turn: int, info: str, allies: Optional[list[dict]]) -> None: ...
    async def show_night_deaths(self, state: GameState, deaths: tuple[str, ...]) -> None: ...
    async def show_public_message(self, state: GameState, author: str, text: str) -> None: ...
    async def public_message(self, state: GameState, player_id: str) -> Optional[str]: ...
    async def private_partners(self, state: GameState, player_id: str) -> Optional[list[str]]: ...
    async def agent_invitation(self, state: GameState, player_id: str, agent_id: str) -> bool: ...
    async def private_message(self, state: GameState, player_id: str) -> Optional[str]: ...
    async def show_private_replies(self, state: GameState, replies: list[tuple[str, str]]) -> None: ...
    async def show_agent_meeting(self, state: GameState, agent_ids: tuple[str, str]) -> None: ...
    async def vote(self, state: GameState, player_id: str) -> Optional[str]: ...


def _human_must_choose(state: GameState, player_id: str) -> bool:
    return any(pid == player_id and needs for pid, needs in night_steps(state))


def _role_infos(memory: MemoryManager, human_id: str, turn: int) -> list[str]:
    """Infos privées écrites pendant ce tour pour le joueur humain (première nuit, Voyante, Détective)."""
    return [
        event.content
        for event in memory.events_for(human_id)
        if event.type == EventType.role_info
        and event.turn == turn
        and event.visible_to == frozenset({human_id})
    ]


def _allies(state: GameState, human_id: str) -> Optional[list[dict]]:
    """Camp du mal : les alliés révélés en première nuit. None pour le camp du bien."""
    if state.player(human_id).role.team not in (Equipe.DEMON, Equipe.SBIRE):
        return None
    return [
        {"id": p.id, "role": p.role.name_FR}
        for p in state.players
        if p.id != human_id and p.role.team in (Equipe.DEMON, Equipe.SBIRE)
    ]


async def _parallel_replies(
    human_id: str,
    partners: list,
    memory: MemoryManager,
) -> list[tuple[str, str]]:
    """Chaque partenaire répond à la fois, à partir du même contexte.
    Les réponses sont enregistrées ensuite, dans l'ordre des partenaires."""
    participants = {human_id} | {agent.player_id for agent in partners}

    async def ask(agent):
        # speak_private attend des identifiants et récupère les noms lui-même
        others = sorted(participants - {agent.player_id})
        try:
            return agent.player_id, await agent.speak_private(others)
        except Exception:
            # Filet de sécurité : cet agent ne répond pas, les autres répondent quand même.
            logger.exception("%s n'a pas pu répondre en privé", agent.player_id)
            return agent.player_id, None

    results = await asyncio.gather(*(ask(agent) for agent in partners))
    replies = []
    for pid, text in results:
        if text is None:
            continue
        memory.add_private(EventType.private_summary, pid, text, participants)
        replies.append((pid, text))
    return replies


async def _agent_invitation(
    state: GameState,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
) -> list:
    """L'humain n'a rien décidé à temps : un seul agent (vivant ou mort) lui propose un entretien.
    Renvoie [agent] si l'humain accepte, [] s'il refuse."""
    if not agents:
        return []
    agent = choose_agent_for_human(list(agents.values()), human_id, memory)
    accepted = await human.agent_invitation(state, human_id, agent.player_id)
    return [agent] if accepted else []


async def _agent_whisper(
    state: GameState,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
    rng: random.Random,
    busy: set[str],
) -> Optional[asyncio.Task]:
    """Deux agents hors du salon de l'humain (vivants ou morts) s'entretiennent en privé.
    L'entretien est annoncé tout de suite ; les résumés (un appel LLM) s'écrivent en tâche de fond,
    pendant que l'humain discute. Renvoie cette tâche, ou None si aucun duo n'est possible."""
    pair = choose_whisper_pair(state, [pid for pid in agents if pid not in busy], human_id, memory, rng)
    if pair is None:
        return None
    memory.add_meeting(list(pair))
    await human.show_agent_meeting(state, pair)
    return asyncio.create_task(write_whisper_summaries(state, memory, pair))


async def _private_channel(
    state: GameState,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
    rng: random.Random,
) -> None:
    """Salon privé facultatif : l'humain choisit 1 ou 2 agents (vivants ou morts), puis échange
    au plus MAX_HUMAN_PRIVATE_MESSAGES messages. À chaque message de l'humain, les agents
    répondent en parallèle.
    Sans décision de l'humain, un agent lui propose un entretien ; s'il accepte, l'agent parle en premier.
    Pendant ce salon, deux autres agents s'entretiennent en privé (aucun si l'humain n'ouvre pas de salon)."""
    partner_ids = await human.private_partners(state, human_id)
    invited = partner_ids is None
    if invited:
        partners = await _agent_invitation(state, agents, memory, human_id, human)
    else:
        partners = [agents[pid] for pid in partner_ids[:MAX_PRIVATE_PARTNERS] if pid in agents]
    if not partners:
        return

    participants = {human_id} | {agent.player_id for agent in partners}
    opening = await start_private_conversation(human_id, partners, memory, agent_speaks_first=invited)
    if opening:
        await human.show_private_replies(state, opening)
    whisper = await _agent_whisper(state, agents, memory, human_id, human, rng, participants)
    try:
        for _ in range(MAX_HUMAN_PRIVATE_MESSAGES):
            text = await human.private_message(state, human_id)
            if not text:
                break
            memory.add_private(EventType.private_summary, human_id, text, participants)
            replies = await _parallel_replies(human_id, partners, memory)
            await human.show_private_replies(state, replies)
    except BaseException:
        if whisper is not None:
            whisper.cancel()  # partie abandonnée : pas d'appel LLM orphelin
        raise
    if whisper is not None:
        await whisper  # les deux agents votent en se souvenant de leur conversation


async def play_turn_with_human(
    state: GameState,
    rng: random.Random,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
) -> TurnResult:
    """Tour complet avec un humain et les IA. Les IA répondent d'abord, puis l'humain,
    à chaque étape, pour que personne n'écrive pendant qu'un appel IA est en cours."""
    if state.phase != Phase.NUIT:
        raise ValueError("un tour commence par la nuit")

    # NUIT : infos de première nuit de l'humain (alliés inclus), IA en parallèle, puis l'humain
    memory.set_moment(state.turn, state.phase)
    allies = _allies(state, human_id) if state.turn == 1 else None
    shown = _role_infos(memory, human_id, state.turn)
    for info in shown:
        await human.show_night_info(state, state.turn, info, allies)
        allies = None

    ai_night = await collect_ai_night_choices(state, agents)
    human_night: dict[str, tuple[str, ...]] = {}
    if _human_must_choose(state, human_id):
        human_night[human_id] = await human.night_choice(state, human_id)
    night_answers = {**ai_night, **human_night}
    after_night, night_choices = play_night(state, rng, lambda s, pid: night_answers.get(pid, ()))
    record_night_choices(after_night, night_choices, memory)
    reveal_psychic_answer(after_night, night_choices, memory, rng)

    night_deaths = _deaths(state, after_night)
    record_night_deaths(after_night, night_deaths, memory)
    await human.show_night_deaths(after_night, night_deaths)

    # Infos écrites pendant la nuit (réponse de la Voyante), hors celles déjà montrées
    for info in _role_infos(memory, human_id, state.turn)[len(shown):]:
        await human.show_night_info(after_night, state.turn, info, None)

    if winner(after_night) is not None:
        return TurnResult(after_night, night_choices, {}, None, night_deaths, winner(after_night))

    # DISCUSSION : IA entre elles, puis l'humain (vivant ou mort)
    discussion = after_night.next_phase()
    memory.set_moment(discussion.turn, discussion.phase)
    speakers = [agents[p.id] for p in discussion.players if p.id in agents]
    said = await public_conversation(speakers, memory)
    for author, text in said:
        await human.show_public_message(discussion, author, text)

    text = await human.public_message(discussion, human_id)
    if text:
        memory.add_public(EventType.public_message, human_id, text)
    await _private_channel(discussion, agents, memory, human_id, human, rng)

    # VOTE : IA en parallèle, puis l'humain (un mort vote par vote fantôme)
    day_state = discussion.next_phase()
    memory.set_moment(day_state.turn, day_state.phase)
    ai_votes = await collect_ai_votes(day_state, agents)
    human_vote: dict[str, Optional[str]] = {}
    if day_state.player(human_id).can_vote:
        human_vote[human_id] = await human.vote(day_state, human_id)
    vote_answers = {**ai_votes, **human_vote}
    after_day, votes, executed = play_day(day_state, lambda s, pid: vote_answers.get(pid))
    record_vote(day_state, votes, executed, memory)
    game_winner = winner(after_day)
    if game_winner is None:
        after_day = after_day.next_phase()
    return TurnResult(after_day, night_choices, votes, executed, night_deaths, game_winner)