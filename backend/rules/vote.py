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

# --- Vote sur une désignation -------------------------------------------------------
# Pendant le jour, un joueur vivant désigne un joueur vivant. Chaque joueur qui peut voter
# répond « pour » (exécuter) ou « contre ». Bulletin : True = pour, False = contre.


def check_nomination(state: GameState, nominator_id: str, nominee_id: str) -> None:
    """Seul un joueur vivant peut désigner, et seulement un joueur vivant."""
    if not state.player(nominator_id).alive:
        raise ValueError(f"{state.player(nominator_id).name} est mort et ne peut pas désigner.")
    if not state.player(nominee_id).alive:
        raise ValueError(f"{state.player(nominee_id).name} est mort et ne peut pas être désigné.")


def _as_votes(nominee_id: str, ballots: dict[str, bool]) -> dict[str, Optional[str]]:
    """Bulletins pour/contre -> votes du moteur (« pour » = cible, « contre » = None)."""
    return {voter: (nominee_id if yes else None) for voter, yes in ballots.items()}


def nomination_result(state: GameState, nominee_id: str, ballots: dict[str, bool]) -> Optional[str]:
    """Renvoie l'id exécuté, ou None. Exécution si les « pour » sont strictement plus de la moitié
    des joueurs vivants (égalité = personne).
    Un mort ne compte que s'il vote « pour » (il utilise alors son vote fantôme) : son « contre »
    ne change rien, sinon il pourrait peser sur chaque vote sans jamais perdre sa voix.
    La règle du Majordome s'applique : sans le « pour » de son maître, son « pour » ne compte pas."""
    votes = filter_butler_votes(state, _as_votes(nominee_id, ballots))
    for voter_id, target_id in votes.items():
        if target_id is not None:
            _check_vote(state, voter_id, target_id)
    yes = sum(1 for target_id in votes.values() if target_id is not None)
    living = sum(1 for player in state.players if player.alive)
    if yes * 2 > living:
        return nominee_id
    return None


def resolve_nomination(state: GameState, nominee_id: str, ballots: dict[str, bool]) -> GameState:
    """Applique le vote sur la désignation : un mort qui vote « pour » utilise son vote fantôme,
    puis le joueur désigné est exécuté s'il a la majorité."""
    executed = nomination_result(state, nominee_id, ballots)
    votes = filter_butler_votes(state, _as_votes(nominee_id, ballots))
    for voter_id, target_id in votes.items():
        voter = state.player(voter_id)
        if target_id is not None and not voter.alive:
            state = state.replace_player(voter.use_ghost_vote())
    if executed is not None:
        state = state.replace_player(state.player(executed).die())
    return state
