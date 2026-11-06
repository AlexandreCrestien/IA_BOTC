import asyncio
import logging
import random
from typing import Any, Optional

from backend.conversations import _rule_for, public_conversation
from backend.game_engine import (TurnResult, _deaths, announce_night, announce_nomination, announce_vote,
                                 play_day, play_night, reveal_psychic_answer)
from backend.memory_manager import MemoryManager, game_master
from backend.models import EventType, GameState, Phase
from backend.rules import legal_actions, night_steps, resolve_nomination, nomination_result, winner

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


async def collect_ai_nomination(
    state: GameState,
    agents: dict[str, Any],
    nominators: frozenset[str] = frozenset(),
    nominees: frozenset[str] = frozenset(),
) -> Optional[tuple[str, str]]:
    """Demande aux agents vivants, dans l'ordre de parole, s'ils veulent désigner quelqu'un (facultatif).
    Renvoie (id de celui qui désigne, id du joueur désigné) pour la première désignation, ou None.
    Un mort ne peut pas désigner, et seul un vivant peut être désigné.
    Chaque joueur désigne au plus une fois par jour (nominators) et n'est désigné qu'une fois par jour (nominees)."""
    living_agents = sorted(
        (agents[p.id] for p in state.players if p.alive and p.id in agents and p.id not in nominators),
        key=lambda agent: _rule_for(agent)["order"],
    )
    for agent in living_agents:
        options = [p.name for p in state.players
                   if p.alive and p.id != agent.player_id and p.id not in nominees]
        if not options:
            continue
        try:
            name = await agent.nominate(options)
        except Exception:
            logger.exception("%s n'a pas pu désigner", agent.player_id)
            continue
        if name is not None and name in options:
            return agent.player_id, _id_of(state, name)
    return None


async def _ballot(agent: Any, nominee_name: str, player_id: str) -> bool:
    try:
        return bool(await agent.vote_on(nominee_name))
    except Exception:
        logger.exception("%s n'a pas pu voter", player_id)
        return False


async def collect_ai_ballots(state: GameState, agents: dict[str, Any], nominee_id: str) -> dict[str, bool]:
    """Bulletins pour/contre des agents qui peuvent voter, demandés au plus MAX_CONCURRENT_CALLS à la fois.
    Un agent en erreur vote contre."""
    ids = [player.id for player in state.players if player.can_vote and player.id in agents]
    nominee_name = _name_of(state, nominee_id)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    results = await asyncio.gather(
        *(_limited(semaphore, _ballot(agents[pid], nominee_name, pid)) for pid in ids)
    )
    return dict(zip(ids, results))


async def vote_on_nomination(
    state: GameState,
    agents: dict[str, Any],
    memory: MemoryManager,
    nomination: tuple[str, str],
    human_ballot=None,
) -> tuple[GameState, dict[str, Optional[str]], Optional[str]]:
    """Vote immédiat sur une désignation, pendant le jour : chacun vote pour ou contre
    (human_ballot(state) -> {id: bool} pour l'humain).
    Renvoie (état après le vote, votes au format du moteur, joueur exécuté ou None)."""
    nominator_id, nominee_id = nomination
    memory.add_public(EventType.nomination, nominator_id,
                      f"Je désigne {_name_of(state, nominee_id)} pour être exécuté.")
    ballots = await collect_ai_ballots(state, agents, nominee_id)
    if human_ballot is not None:
        ballots.update(await human_ballot(state))
    ordered = {p.id: ballots[p.id] for p in state.players if p.id in ballots}
    executed = nomination_result(state, nominee_id, ordered)
    after = resolve_nomination(state, nominee_id, ordered)
    announce_nomination(memory, state, nominee_id, ordered, executed)
    votes = {voter: (nominee_id if yes else None) for voter, yes in ordered.items()}
    return after, votes, executed


async def final_vote(
    state: GameState,
    agents: dict[str, Any],
    memory: MemoryManager,
    human_vote=None,
) -> tuple[GameState, dict[str, Optional[str]], Optional[str]]:
    """Vote de fin de jour (state en phase VOTE), quand personne n'a été exécuté sur désignation :
    chaque joueur qui peut voter choisit qui doit mourir, ou personne.
    Exécution si un joueur obtient plus de la moitié des votes exprimés (égalité : personne).
    human_vote(state) -> {id: cible ou None} pour l'humain.
    Renvoie (état après le vote, votes, joueur exécuté ou None)."""
    memory.add_public(EventType.announcement, game_master,
                      "Fin du jour : chacun vote pour le joueur qui doit être exécuté (ou pour personne).")
    votes = await collect_ai_votes(state, agents)
    if human_vote is not None:
        votes.update(await human_vote(state))
    ordered = {p.id: votes[p.id] for p in state.players if p.id in votes}
    after, cast, executed = play_day(state, lambda s, pid: ordered.get(pid))
    announce_vote(memory, state, cast, executed)
    return after, cast, executed


async def play_turn_with_ai(
    state: GameState,
    rng: random.Random,
    agents: dict[str, Any],
    memory: MemoryManager,
) -> TurnResult:
    """Tour complet avec les agents IA : nuit, victoire, discussion publique, désignation facultative
    (vote pour/contre), vote de fin de jour si personne n'a été exécuté, victoire.
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

    # Désignation facultative : vote immédiat pour ou contre
    votes, executed = {}, None
    nomination = await collect_ai_nomination(discussion, agents)
    if nomination is not None:
        discussion, votes, executed = await vote_on_nomination(discussion, agents, memory, nomination)

    # VOTE de fin de jour, si personne n'a été exécuté sur désignation
    day_state = discussion.next_phase()
    memory.set_moment(day_state.turn, day_state.phase)
    if executed is None:
        after_day, votes, executed = await final_vote(day_state, agents, memory)
    else:
        after_day = day_state
    game_winner = winner(after_day)
    if game_winner is None:
        after_day = after_day.next_phase()
    return TurnResult(after_day, night_choices, votes, executed, night_deaths, game_winner)