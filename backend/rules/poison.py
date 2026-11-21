from backend.models import Effect, GameState, Phase, RoleKey, EffectType
from backend.rules.actions import legal_actions
from backend.rules.powers import is_poisoned


def poison(state: GameState, poisoner_id: str, target_id: str) -> GameState:
    """Pose le poison de l'Empoisonneur sur une cible légale. Le poison dure jusqu'au début de la nuit suivante.
    Si l'Empoisonneur est poisoned, le choix n'a aucun effet."""
    if target_id not in legal_actions(state, poisoner_id).targets:
        raise ValueError(f"{target_id} n'est pas une cible légale pour {poisoner_id}")
    if is_poisoned(state.player(poisoner_id)):
        return state
    effect = Effect(
        type=EffectType.POISONED,
        source=RoleKey.POISONER,
        turn_start=state.turn,
        phase_start=Phase.NIGHT,
        turn_end=state.turn + 1,
        phase_end=Phase.NIGHT,
    )
    target = state.player(target_id).add_effect(effect)
    return state.replace_player(target)