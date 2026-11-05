from backend.models import GameState
from backend.rules.butler import choose_master
from backend.rules.night_effects import kill, protect
from backend.rules.poison import poison

# Ordre de résolution = ordre de jeu : l'Empoisonneur d'abord, pour qu'un Moine ou un Majordome empoisonné n'ait pas d'effet.
RESOLUTION_ORDER = (
    ("poisoner", poison),
    ("monk", protect),
    ("imp", kill),
    ("butler", choose_master),
)


def resolve_night(state: GameState, choices: dict[str, tuple[str, ...]]) -> GameState:
    """Applique les choix de nuit dans l'ordre de jeu : poison, protection, meurtre, maître du Majordome.
    choices : {id_joueur: cibles}. Un joueur absent du dictionnaire n'agit pas.
    La Voyante ne modifie pas l'état ici."""
    for role_name, apply in RESOLUTION_ORDER:
        for player in state.players:
            if player.role.name_EN != role_name or player.id not in choices:
                continue
            for target_id in choices[player.id]:
                state = apply(state, player.id, target_id)
    return state