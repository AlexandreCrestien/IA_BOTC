from typing import Optional

from backend.models import GameState
from backend.rules.actions import legal_actions
from backend.rules.links import set_link
from backend.rules.powers import is_poisoned

MASTER_KEY = "maitre"


def choose_master(state: GameState, butler_id: str, master_id: str) -> GameState:
    """Enregistre le maître du Majordome pour la nuit. Sans effet si le Majordome est empoisonné."""
    if master_id not in legal_actions(state, butler_id).targets:
        raise ValueError(f"Cible illégale pour le Majordome : {master_id}")
    butler = state.player(butler_id)
    if is_poisoned(butler):
        return state
    return state.replace_player(set_link(butler, MASTER_KEY, master_id))


def master_of(state: GameState, butler_id: str) -> Optional[str]:
    return state.player(butler_id).links.get(MASTER_KEY)


def filter_butler_votes(state: GameState, votes: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    """Un Majordome ne peut voter que si son maître vote. Sinon son vote devient une abstention.
    Un Majordome empoisonné n'est jamais bloqué : son vote passe toujours."""
    filtered = dict(votes)
    for player in state.players:
        if player.role.name_EN != "butler" or player.id not in votes:
            continue
        if is_poisoned(player):
            continue
        master_id = master_of(state, player.id)
        if master_id is None:
            continue
        if votes.get(master_id) is None:
            filtered[player.id] = None
    return filtered