from typing import Optional

from backend.models import GameState, RoleKey
from backend.rules.actions import legal_actions
from backend.rules.links import set_link
from backend.rules.powers import is_poisoned

MASTER_KEY = "master"


def choose_master(state: GameState, valet_id: str, master_id: str) -> GameState:
    """Enregistre le maître du Valet pour la nuit. Sans effet si le Valet est empoisonné."""
    if master_id not in legal_actions(state, valet_id).targets:
        raise ValueError(f"Cible illégale pour le Valet : {master_id}")
    valet = state.player(valet_id)
    if is_poisoned(valet):
        return state
    return state.replace_player(set_link(valet, MASTER_KEY, master_id))


def master_of(state: GameState, valet_id: str) -> Optional[str]:
    return state.player(valet_id).links.get(MASTER_KEY)


def bound_valets(state: GameState) -> dict[str, str]:
    """Valets qui ne peuvent voter que si leur maître vote : {valet: maître}.
    Le moteur les fait voter après les autres, et seulement si leur maître a voté (pas d'appel inutile).
    N'y figurent pas : un Valet qui ne peut pas voter, sans maître, ou empoisonné (jamais bloqué)."""
    return {
        player.id: master_of(state, player.id)
        for player in state.players
        if player.role.name_EN == RoleKey.VALET and player.can_vote
        and master_of(state, player.id) is not None and not is_poisoned(player)
    }


def filter_valet_votes(state: GameState, votes: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    """Un Valet ne peut voter que si son maître vote. Sinon son vote devient une abstention.
    Un Valet empoisonné n'est jamais bloqué : son vote passe toujours."""
    filtered = dict(votes)
    for player in state.players:
        if player.role.name_EN != RoleKey.VALET or player.id not in votes:
            continue
        if is_poisoned(player):
            continue
        master_id = master_of(state, player.id)
        if master_id is None:
            continue
        if votes.get(master_id) is None:
            filtered[player.id] = None
    return filtered