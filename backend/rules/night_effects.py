from backend.models import Effect, GameState, Phase, RoleKey, EffectType
from backend.rules.actions import legal_actions
from backend.rules.powers import is_poisoned


def protect(state: GameState, watchman_id: str, target_id: str) -> GameState:
    """Le Veilleur protège une cible légale jusqu'au début du jour. Sans effet si le Veilleur est bourré."""
    _check_legal(state, watchman_id, target_id)
    if is_poisoned(state.player(watchman_id)):
        return state
    effect = Effect(
        type=EffectType.PROTECTED,
        source=RoleKey.WATCHMAN,
        turn_start=state.turn,
        phase_start=Phase.NIGHT,
        turn_end=state.turn,
        phase_end=Phase.DISCUSSION,
    )
    return state.replace_player(state.player(target_id).add_effect(effect))


def kill(state: GameState, reaper_id: str, target_id: str) -> GameState:
    """Le Faucheur tue une cible légale, sauf si elle est protégée cette nuit ou déjà morte.
    Sans effet si le Faucheur est bourré. Les protections doivent être posées avant les meurtres."""
    _check_legal(state, reaper_id, target_id)
    if is_poisoned(state.player(reaper_id)):
        return state
    target = state.player(target_id)
    if not target.alive or target.has_effect(EffectType.PROTECTED):
        return state
    return state.replace_player(target.die())


def _check_legal(state: GameState, player_id: str, target_id: str) -> None:
    if target_id not in legal_actions(state, player_id).targets:
        raise ValueError(f"{target_id} n'est pas une cible légale pour {player_id}")