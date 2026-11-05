from backend.models import Effect, GameState, Phase, TypeEffet
from backend.rules.actions import legal_actions
from backend.rules.powers import is_poisoned


def protect(state: GameState, monk_id: str, target_id: str) -> GameState:
    """Le Moine protège une cible légale jusqu'au début du jour. Sans effet si le Moine est bourré."""
    _check_legal(state, monk_id, target_id)
    if is_poisoned(state.player(monk_id)):
        return state
    effect = Effect(
        type=TypeEffet.PROTEGE,
        source="monk",
        turn_start=state.turn,
        phase_start=Phase.NUIT,
        turn_end=state.turn,
        phase_end=Phase.DISCUSSION,
    )
    return state.replace_player(state.player(target_id).add_effect(effect))


def kill(state: GameState, imp_id: str, target_id: str) -> GameState:
    """Le Diablotin tue une cible légale, sauf si elle est protégée cette nuit ou déjà morte.
    Sans effet si le Diablotin est bourré. Les protections doivent être posées avant les meurtres."""
    _check_legal(state, imp_id, target_id)
    if is_poisoned(state.player(imp_id)):
        return state
    target = state.player(target_id)
    if not target.alive or target.has_effect(TypeEffet.PROTEGE):
        return state
    return state.replace_player(target.die())


def _check_legal(state: GameState, player_id: str, target_id: str) -> None:
    if target_id not in legal_actions(state, player_id).targets:
        raise ValueError(f"{target_id} n'est pas une cible légale pour {player_id}")