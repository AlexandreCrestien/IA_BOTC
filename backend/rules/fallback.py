import random

from backend.models import GameState
from backend.rules.actions import legal_actions


def random_legal_choice(state: GameState, player_id: str, rng: random.Random) -> tuple[str, ...]:
    """Choix de repli : tire au hasard des cibles parmi les options légales.
    Renvoie un tuple vide si le joueur n'a aucune cible légale : il n'y a alors pas d'action."""
    action = legal_actions(state, player_id)
    if not action.targets:
        return ()
    return tuple(rng.sample(action.targets, min(action.count, len(action.targets))))