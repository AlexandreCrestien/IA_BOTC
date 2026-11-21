"""Choix des agents IA pendant un tour (nuit et vote), demandés ensemble.
Les agents parlent en noms ; ces fonctions traduisent en identifiants pour le moteur (backend/engine/turn.py)."""
import asyncio
import logging
from typing import Any, Optional

from backend.models import GameState
from backend.rules import legal_actions, night_steps, vote_targets

logger = logging.getLogger(__name__)

def _name_of(state: GameState, player_id: str) -> str:
    return state.player(player_id).name


def _id_of(state: GameState, name: str) -> str:
    for player in state.players:
        if player.name == name:
            return player.id
    raise ValueError(f"nom inconnu : {name}")


def night_situation(state: GameState) -> str:
    alive = ", ".join(p.name for p in state.alive_players())
    return (f"Joueurs vivants : {alive}. "
            "Ce que tu sais contient tes choix des nuits précédentes : ne répète pas un choix sans information nouvelle.")


async def _night_choice(agent: Any, state: GameState, player_id: str) -> tuple[str, ...]:
    legal = legal_actions(state, player_id)
    options = [_name_of(state, target) for target in legal.targets]
    try:
        names = await agent.night_action(options, legal.count, night_situation(state))
        return tuple(_id_of(state, name) for name in names)
    except Exception:
        logger.exception("%s n'a pas pu choisir cette nuit", player_id)
        return ()


async def collect_ai_night_choices(state: GameState, agents: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Choix de nuit des agents IA, demandés ensemble (llm_client limite le nombre d'appels simultanés).
    Les choix sont secrets et indépendants : leurs effets sont appliqués ensuite par resolve_night."""
    ids = [player_id for player_id, needs_choice in night_steps(state)
           if needs_choice and player_id in agents]
    results = await asyncio.gather(*(_night_choice(agents[pid], state, pid) for pid in ids))
    return dict(zip(ids, results))


async def _vote(agent: Any, state: GameState, player_id: str) -> Optional[str]:
    options = [state.player(target).name for target in vote_targets(state, player_id)]
    try:
        name = await agent.vote(options)
        return None if name is None else _id_of(state, name)
    except Exception:
        logger.exception("%s n'a pas pu voter", player_id)
        return None


async def collect_ai_votes(state: GameState, agents: dict[str, Any]) -> dict[str, Optional[str]]:
    """Votes des agents IA, demandés ensemble (llm_client limite le nombre d'appels simultanés).
    Un agent en erreur s'abstient."""
    ids = [player.id for player in state.players if player.can_vote and player.id in agents]
    results = await asyncio.gather(*(_vote(agents[pid], state, pid) for pid in ids))
    return dict(zip(ids, results))
