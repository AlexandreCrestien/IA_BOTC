import asyncio
import logging
import random
from typing import Any, Optional

from backend.conversations import public_conversation
from backend.game_engine import (TurnResult, _deaths, announce_night, announce_vote, play_day, play_night,
                                 reveal_psychic_answer)
from backend.memory_manager import MemoryManager
from backend.models import GameState, Phase
from backend.rules import legal_actions, night_steps, winner

logger = logging.getLogger(__name__)

# Nombre maximum d'appels LLM simultanés (quota Groq : 8000 TPM).
MAX_CONCURRENT_CALLS = 2


def check_unique_names(names: dict[str, str]) -> None:
    """Les noms servent à traduire les réponses des IA : ils doivent être uniques."""
    if len(set(names.values())) != len(names):
        raise ValueError("noms de joueurs en double")


def _name_of(state: GameState, player_id: str) -> str:
    return state.player(player_id).name


def _id_of(state: GameState, name: str) -> str:
    for player in state.players:
        if player.name == name:
            return player.id
    raise ValueError(f"nom inconnu : {name}")


async def _limited(semaphore: asyncio.Semaphore, awaitable):
    """Attend une place libre dans le sémaphore avant de lancer l'appel."""
    async with semaphore:
        return await awaitable


async def _night_choice(agent: Any, state: GameState, player_id: str) -> tuple[str, ...]:
    legal = legal_actions(state, player_id)
    options = [_name_of(state, target) for target in legal.targets]
    try:
        names = await agent.night_action(options, legal.count)
        return tuple(_id_of(state, name) for name in names)
    except Exception:
        logger.exception("%s n'a pas pu choisir cette nuit", player_id)
        return ()


async def collect_ai_night_choices(state: GameState, agents: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Choix de nuit des agents IA, demandés au plus MAX_CONCURRENT_CALLS à la fois.
    Les choix sont secrets et indépendants : leurs effets sont appliqués ensuite par resolve_night."""
    ids = [player_id for player_id, needs_choice in night_steps(state)
           if needs_choice and player_id in agents]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    results = await asyncio.gather(
        *(_limited(semaphore, _night_choice(agents[pid], state, pid)) for pid in ids)
    )
    return dict(zip(ids, results))


async def _vote(agent: Any, state: GameState, player_id: str) -> Optional[str]:
    options = [player.name for player in state.players if player.alive]
    try:
        name = await agent.vote(options)
        return None if name is None else _id_of(state, name)
    except Exception:
        logger.exception("%s n'a pas pu voter", player_id)
        return None


async def collect_ai_votes(state: GameState, agents: dict[str, Any]) -> dict[str, Optional[str]]:
    """Votes des agents IA, demandés au plus MAX_CONCURRENT_CALLS à la fois.
    Un agent en erreur s'abstient."""
    ids = [player.id for player in state.players if player.can_vote and player.id in agents]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    results = await asyncio.gather(
        *(_limited(semaphore, _vote(agents[pid], state, pid)) for pid in ids)
    )
    return dict(zip(ids, results))


async def play_turn_with_ai(
    state: GameState,
    rng: random.Random,
    agents: dict[str, Any],
    memory: MemoryManager,
) -> TurnResult:
    """Tour complet avec les agents IA : nuit, victoire, discussion publique, vote, victoire.
    La mémoire suit la phase courante, pour que chaque message soit daté correctement.
    Les joueurs sans agent (l'humain) reçoivent un choix aléatoire ou une abstention."""
    if state.phase != Phase.NUIT:
        raise ValueError("un tour commence par la nuit")

    memory.set_moment(state.turn, state.phase)
    ai_night = await collect_ai_night_choices(state, agents)
    after_night, night_choices = play_night(state, rng, lambda s, pid: ai_night.get(pid, ()))
    reveal_psychic_answer(after_night, night_choices, memory, rng)    
    night_deaths = _deaths(state, after_night)
    memory.set_moment(after_night.turn, Phase.DISCUSSION)  # l'annonce du matin est datée du jour
    announce_night(memory, after_night, night_deaths)
    if winner(after_night) is not None:
        return TurnResult(after_night, night_choices, {}, None, night_deaths, winner(after_night))

    # DISCUSSION : les agents vivants parlent publiquement avant le vote
    discussion = after_night.next_phase()
    memory.set_moment(discussion.turn, discussion.phase)
    speakers = [agents[p.id] for p in discussion.players if p.id in agents]
    await public_conversation(speakers, memory)

    # VOTE
    day_state = discussion.next_phase()
    memory.set_moment(day_state.turn, day_state.phase)
    ai_votes = await collect_ai_votes(day_state, agents)
    after_day, votes, executed = play_day(day_state, lambda s, pid: ai_votes.get(pid))
    announce_vote(memory, day_state, votes, executed)
    game_winner = winner(after_day)
    if game_winner is None:
        after_day = after_day.next_phase()
    return TurnResult(after_day, night_choices, votes, executed, night_deaths, game_winner)