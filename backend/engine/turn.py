"""Tour de jeu : la seule boucle du moteur, utilisée par le serveur, les scripts et les tests.
Le joueur sans agent IA (l'humain) passe par un HumanPort : le WebSocket (QueueHumanPort), le terminal,
ou un joueur automatique pour les parties « IA seules » (AutoHumanPort).
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

from backend.ai.agent_whispers import choose_whisper_pair, write_whisper_summaries
from backend.ai.choices import collect_ai_night_choices, collect_ai_votes
from backend.ai.conversations import (
    choose_agent_for_human,
    private_replies,
    public_conversation,
    start_private_conversation,
)
from backend.engine.steps import (
    TurnResult,
    deaths_between,
    play_day,
    play_night,
    record_night_choices,
    record_night_deaths,
    record_vote,
    reveal_medium_answer,
)
from backend.ai.memory_manager import MemoryManager
from backend.models import Team, EventType, GameState, Phase
from backend.rules import night_steps, winner

logger = logging.getLogger(__name__)

MAX_HUMAN_PRIVATE_MESSAGES = 3
MAX_PRIVATE_PARTNERS = 2


class HumanPort(Protocol):
    """Interface entre le moteur et l'humain. Chaque méthode attend la réponse de l'humain.
    None signifie « rien » : pas de message, pas de salon privé, abstention.
    Les méthodes show_* transmettent l'état courant, pour que le front affiche la bonne phase.
    private_partners : [] si l'humain ne veut pas de salon privé, None s'il n'a rien décidé à temps
    (un agent vient alors lui proposer un entretien, voir agent_invitation).
    show_agent_unavailable : l'IA d'un agent n'a pas répondu ; step = "night", "public", "private" ou "vote".
    Le port décide quoi montrer (rien pour la nuit : ce serait révéler que l'agent a un pouvoir)."""

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
    async def show_agent_unavailable(self, state: GameState, agent_id: str, step: str) -> None: ...


def _human_must_choose(state: GameState, player_id: str) -> bool:
    return any(pid == player_id and needs for pid, needs in night_steps(state))


def _role_infos(memory: MemoryManager, human_id: str, turn: int) -> list[str]:
    """Infos privées écrites pendant ce tour pour le joueur humain (première nuit, Médium, Inquisiteur)."""
    return [
        event.content
        for event in memory.events_for(human_id)
        if event.type == EventType.ROLE_INFO
        and event.turn == turn
        and event.visible_to == frozenset({human_id})
    ]


def _allies(state: GameState, human_id: str) -> Optional[list[dict]]:
    """Camp du mal : les alliés révélés en première nuit. None pour le camp du bien."""
    if state.player(human_id).role.team not in (Team.DEMON, Team.ACCOMPLICE):
        return None
    return [
        {"id": p.id, "role": p.role.name_FR}
        for p in state.players
        if p.id != human_id and p.role.team in (Team.DEMON, Team.ACCOMPLICE)
    ]


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


async def _report_failures(state: GameState, human: HumanPort, agent_ids, step: str) -> None:
    for agent_id in agent_ids:
        await human.show_agent_unavailable(state, agent_id, step)


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
    failures: list[str] = []
    opening = await start_private_conversation(human_id, partners, memory, agent_speaks_first=invited,
                                               failures=failures)
    if opening:
        await human.show_private_replies(state, opening)
    await _report_failures(state, human, failures, "private")
    whisper = await _agent_whisper(state, agents, memory, human_id, human, rng, participants)
    try:
        for _ in range(MAX_HUMAN_PRIVATE_MESSAGES):
            text = await human.private_message(state, human_id)
            if not text:
                break
            memory.add_private(EventType.PRIVATE_SUMMARY, human_id, text, participants)
            failures = []
            replies = await private_replies(human_id, partners, memory, failures=failures)
            await human.show_private_replies(state, replies)
            await _report_failures(state, human, failures, "private")
    except BaseException:
        if whisper is not None:
            whisper.cancel()  # partie abandonnée : pas d'appel LLM orphelin
        raise
    if whisper is not None:
        await whisper  # les deux agents votent en se souvenant de leur conversation


async def play_turn(
    state: GameState,
    rng: random.Random,
    agents: dict,
    memory: MemoryManager,
    human_id: str,
    human: HumanPort,
) -> TurnResult:
    """Tour complet : nuit, contrôle de victoire, discussion, vote, contrôle de victoire.
    Les IA répondent d'abord, puis l'humain, à chaque étape, pour que personne n'écrive
    pendant qu'un appel IA est en cours. Passe à la nuit suivante si la partie continue."""
    if state.phase != Phase.NIGHT:
        raise ValueError("un tour commence par la nuit")

    # NUIT : infos de première nuit de l'humain (alliés inclus), IA en parallèle, puis l'humain
    memory.set_moment(state.turn, state.phase)
    allies = _allies(state, human_id) if state.turn == 1 else None
    shown = _role_infos(memory, human_id, state.turn)
    for info in shown:
        await human.show_night_info(state, state.turn, info, allies)
        allies = None

    night_failures: list[str] = []
    ai_night = await collect_ai_night_choices(state, agents, failures=night_failures)
    await _report_failures(state, human, night_failures, "night")
    human_night: dict[str, tuple[str, ...]] = {}
    if _human_must_choose(state, human_id):
        human_night[human_id] = await human.night_choice(state, human_id)
    night_answers = {**ai_night, **human_night}
    after_night, night_choices = play_night(state, rng, lambda s, pid: night_answers.get(pid, ()))
    record_night_choices(after_night, night_choices, memory)
    reveal_medium_answer(after_night, night_choices, memory, rng)

    night_deaths = deaths_between(state, after_night)
    record_night_deaths(after_night, night_deaths, memory)
    await human.show_night_deaths(after_night, night_deaths)

    # Infos écrites pendant la nuit (réponse du Médium), hors celles déjà montrées
    for info in _role_infos(memory, human_id, state.turn)[len(shown):]:
        await human.show_night_info(after_night, state.turn, info, None)

    if winner(after_night) is not None:
        return TurnResult(after_night, night_choices, {}, None, night_deaths, winner(after_night))

    # DISCUSSION : IA entre elles, puis l'humain (vivant ou mort)
    discussion = after_night.next_phase()
    memory.set_moment(discussion.turn, discussion.phase)
    speakers = [agents[p.id] for p in discussion.players if p.id in agents]
    public_failures: list[tuple[int, str]] = []
    said = await public_conversation(speakers, memory, failures=public_failures)
    # Messages et silences dans l'ordre où ils se sont produits
    for position, (author, text) in enumerate(said):
        await _report_failures(discussion, human, [pid for at, pid in public_failures if at == position], "public")
        await human.show_public_message(discussion, author, text)
    await _report_failures(discussion, human, [pid for at, pid in public_failures if at >= len(said)], "public")

    text = await human.public_message(discussion, human_id)
    if text:
        memory.add_public(EventType.PUBLIC_MESSAGE, human_id, text)
    await _private_channel(discussion, agents, memory, human_id, human, rng)

    # VOTE : IA en parallèle, puis l'humain (un mort vote par voix d'outre-tombe)
    day_state = discussion.next_phase()
    memory.set_moment(day_state.turn, day_state.phase)
    vote_failures: list[str] = []
    ai_votes = await collect_ai_votes(day_state, agents, failures=vote_failures)
    await _report_failures(day_state, human, vote_failures, "vote")
    human_vote: dict[str, Optional[str]] = {}
    if day_state.player(human_id).can_vote:
        human_vote[human_id] = await human.vote(day_state, human_id)
    vote_answers = {**ai_votes, **human_vote}
    after_day, votes, executed = play_day(day_state, lambda s, pid: vote_answers.get(pid))
    record_vote(day_state, votes, executed, memory)
    game_winner = winner(after_day)
    if game_winner is None:
        after_day = after_day.next_phase()
    return TurnResult(after_day, night_choices, votes, executed, night_deaths, game_winner,
                      frozenset(vote_failures))