from typing import NamedTuple

from backend.models import GameState, Phase


class LegalAction(NamedTuple):
    """Cibles légales d'un joueur pour son action de nuit."""
    targets: tuple[str, ...]
    count: int  # nombre de cibles à choisir


# Rôles qui peuvent se désigner eux-mêmes.
CAN_TARGET_SELF = {"psychic"}
# Nombre de cibles par rôle (1 par défaut).
TARGET_COUNT = {"psychic": 2}


def legal_actions(state: GameState, player_id: str) -> LegalAction:
    """Cibles possibles pour l'action de nuit d'un joueur. Vide si le joueur ne peut pas agir maintenant."""
    player = state.player(player_id)
    if state.phase != Phase.NUIT or not player.can_act:
        return LegalAction(targets=(), count=0)

    role_name = player.role.name_EN
    targets = [
        other.id
        for other in state.players
        if other.id != player_id or role_name in CAN_TARGET_SELF
    ]
    return LegalAction(targets=tuple(targets), count=TARGET_COUNT.get(role_name, 1))