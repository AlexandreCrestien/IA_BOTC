import random

from backend.models import Team, GameState, Player, EffectType

# Clé de lien qui désigne le leurre du Médium.
FALSE_LEAD_KEY = "false_lead"


def is_poisoned(player: Player) -> bool:
    """Un joueur empoisonné est « poisoned » : son pouvoir n'a aucun effet, et il ne le sait pas."""
    return player.has_effect(EffectType.POISONED)


def medium_answer(state: GameState, viewer_id: str, probed_ids: tuple[str, ...], rng: random.Random) -> bool:
    """Réponse du Médium : True si au moins un des joueurs sondés est démon,
    le leurre comptant comme démon. Réponse au hasard si le Médium est empoisonné."""
    viewer = state.player(viewer_id)
    if is_poisoned(viewer):
        return rng.random() < 0.5
    false_lead = viewer.link(FALSE_LEAD_KEY)
    for player_id in probed_ids:
        if state.player(player_id).role.team == Team.DEMON or player_id == false_lead:
            return True
    return False