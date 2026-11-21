from backend.models import GameState, RoleKey
from backend.rules.actions import legal_actions

# Ordre des rôles, défini par le groupe.
FIRST_NIGHT_ORDER = (RoleKey.POISONER, RoleKey.PSYCHIC, RoleKey.DETECTIVE, RoleKey.BUTLER)
OTHER_NIGHT_ORDER = (RoleKey.POISONER, RoleKey.MONK, RoleKey.IMP, RoleKey.PSYCHIC, RoleKey.BUTLER)


def night_steps(state: GameState) -> list[tuple[str, bool]]:
    """Étapes de la nuit, dans l'ordre : (id du joueur, appel LLM ou non).
    Le Détective apparaît en première nuit sans appel LLM : le moteur lui donne son information."""
    order = FIRST_NIGHT_ORDER if state.turn == 1 else OTHER_NIGHT_ORDER
    steps = []
    for role_name in order:
        for player in state.players:
            if player.role.name_EN != role_name:
                continue
            if role_name == RoleKey.DETECTIVE:
                steps.append((player.id, False))
            elif legal_actions(state, player.id).targets:
                steps.append((player.id, True))
    return steps