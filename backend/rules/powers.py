import random

from backend.models import Equipe, GameState, Player, TypeEffet

# Clé de lien qui désigne le leurre de la Voyante.
FALSE_LEAD_KEY = "fausse_piste"


def is_drunk(player: Player) -> bool:
    """Un joueur empoisonné est « bourré » : son pouvoir n'a aucun effet, et il ne le sait pas."""
    return player.has_effect(TypeEffet.EMPOISONNE)


def psychic_answer(state: GameState, viewer_id: str, probed_ids: tuple[str, ...], rng: random.Random) -> bool:
    """Réponse de la Voyante : True si au moins un des joueurs sondés est démon,
    le leurre comptant comme démon. Réponse au hasard si la Voyante est bourrée."""
    viewer = state.player(viewer_id)
    if is_drunk(viewer):
        return rng.random() < 0.5
    false_lead = viewer.link(FALSE_LEAD_KEY)
    for player_id in probed_ids:
        if state.player(player_id).role.team == Equipe.DEMON or player_id == false_lead:
            return True
    return False