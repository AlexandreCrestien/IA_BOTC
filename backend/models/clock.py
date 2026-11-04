from backend.models.enums import Phase

# Ordre chronologique à l'intérieur d'un tour : la nuit précède le jour.
PHASE_ORDER = {Phase.NUIT: 0, Phase.DISCUSSION: 1, Phase.VOTE: 2}


def instant(turn: int, phase: Phase) -> int:
    """Transforme un couple (tour, phase) en entier croissant, pour comparer deux moments."""
    return turn * 3 + PHASE_ORDER[phase]