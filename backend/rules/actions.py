from typing import NamedTuple

from backend.models import GameState, Phase


class LegalAction(NamedTuple):
    """Cibles légales d'un joueur pour son action de nuit."""
    targets: tuple[str, ...]
    count: int  # nombre de cibles à choisir


def legal_actions(state: GameState, player_id: str) -> LegalAction:
    """Cibles possibles pour l'action de nuit d'un joueur. Vide si le joueur ne peut pas agir maintenant.
    Un joueur mort n'a plus de pouvoir."""
    player = state.player(player_id)
    if state.phase != Phase.NUIT or not player.alive or not player.can_act:
        return LegalAction(targets=(), count=0)

    role = player.role
    targets = [other.id for other in state.players if other.id != player_id or role.can_target_self]
    return LegalAction(targets=tuple(targets), count=role.night_targets)