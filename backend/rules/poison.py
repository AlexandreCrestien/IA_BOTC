from backend.models import Effect, GameState, Phase, RoleKey, EffectType
from backend.rules.actions import legal_actions
from backend.rules.powers import is_poisoned


def poison(state: GameState, apothecary_id: str, target_id: str) -> GameState:
    """Pose le poison de l'Apothicaire sur une cible légale. Le poison dure jusqu'au début de la nuit suivante.
    Si l'Apothicaire est poisoned, le choix n'a aucun effet."""
    if target_id not in legal_actions(state, apothecary_id).targets:
        raise ValueError(f"{target_id} n'est pas une cible légale pour {apothecary_id}")
    if is_poisoned(state.player(apothecary_id)):
        return state
    effect = Effect(
        type=EffectType.POISONED,
        source=RoleKey.APOTHECARY,
        turn_start=state.turn,
        phase_start=Phase.NIGHT,
        turn_end=state.turn + 1,
        phase_end=Phase.NIGHT,
    )
    target = state.player(target_id).add_effect(effect)
    return state.replace_player(target)