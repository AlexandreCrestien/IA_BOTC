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
    Exécution si la cible obtient le plus de voix. Égalité en tête : personne n'est exécuté."""
    return _executed(state, filter_butler_votes(state, votes))


def _executed(state: GameState, votes: dict[str, Optional[str]]) -> Optional[str]:
    """Décompte de votes déjà filtrés (vote du Majordome retiré s'il ne compte pas)."""
    for voter_id, target_id in votes.items():
        if target_id is not None:
            _check_vote(state, voter_id, target_id)

    cast = [target_id for target_id in votes.values() if target_id is not None]
    if not cast:
        return None

    ranking = Counter(cast).most_common()
    top_target, top_count = ranking[0]
    if len(ranking) > 1 and ranking[1][1] == top_count:
        return None
    return top_target


def resolve_vote(state: GameState, votes: dict[str, Optional[str]]) -> GameState:
    """Applique le vote : consomme le vote fantôme des morts qui ont voté, puis exécute si besoin.
    L'abstention ne consomme pas le vote fantôme."""
    votes = filter_butler_votes(state, votes)
    executed = _executed(state, votes)

    for voter_id, target_id in votes.items():
        if target_id is None:
            continue
        voter = state.player(voter_id)
        if not voter.alive:
            state = state.replace_player(voter.use_ghost_vote())

    if executed is not None:
        state = state.replace_player(state.player(executed).die())
    return state