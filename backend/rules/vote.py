from collections import Counter
from typing import Optional

from backend.models import GameState
from backend.rules.butler import filter_butler_votes

# Un vote vaut une cible (id de joueur). None = abstention, qui n'est pas comptée.


def _check_vote(state: GameState, voter_id: str, target_id: str) -> None:
    voter = state.player(voter_id)
    if not voter.can_vote:
        raise ValueError(f"{voter.name} ne peut pas voter.")
    target = state.player(target_id)
    if not target.alive:
        raise ValueError(f"{target.name} est mort et ne peut pas être désigné.")


def vote_result(state: GameState, votes: dict[str, Optional[str]]) -> Optional[str]:
    """Renvoie l'id du joueur exécuté, ou None.
    Exécution si la cible obtient strictement plus de la moitié des votes exprimés."""
    votes = filter_butler_votes(state, votes)

    for voter_id, target_id in votes.items():
        if target_id is not None:
            _check_vote(state, voter_id, target_id)

    cast = [target_id for target_id in votes.values() if target_id is not None]
    if not cast:
        return None

    target_id, count = Counter(cast).most_common(1)[0]
    if count * 2 > len(cast):
        return target_id
    return None


def resolve_vote(state: GameState, votes: dict[str, Optional[str]]) -> GameState:
    """Applique le vote : consomme le vote fantôme des morts qui ont voté, puis exécute si besoin.
    L'abstention ne consomme pas le vote fantôme."""
    votes = filter_butler_votes(state, votes)
    executed = vote_result(state, votes)

    for voter_id, target_id in votes.items():
        if target_id is None:
            continue
        voter = state.player(voter_id)
        if not voter.alive:
            state = state.replace_player(voter.use_ghost_vote())

    if executed is not None:
        state = state.replace_player(state.player(executed).die())
    return state