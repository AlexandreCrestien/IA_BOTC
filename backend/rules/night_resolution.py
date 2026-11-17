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
    """Applique les choix de nuit dans l'ordre de jeu. Un joueur tué plus tôt dans la nuit
    annule son action : son choix n'a aucun effet."""
    for role_name, apply in RESOLUTION_ORDER:
        for player in state.players:
            if player.role.name_EN != role_name or player.id not in choices:
                continue
            for target_id in choices[player.id]:
                if not state.player(player.id).alive:
                    break
                state = apply(state, player.id, target_id)
    return state