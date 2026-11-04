from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import EventType, Phase


class GameEvent(BaseModel):
    """Une ligne du journal de la partie. Immutable.
    visible_to = None : visible de tous.
    visible_to = ensemble d'ids : visible seulement de ces joueurs.
    visible_to = ensemble vide : visible du moteur seul (leurre, poison, vrais rôles)."""

    model_config = ConfigDict(frozen=True)

    type: EventType
    turn: int = Field(ge=1)
    phase: Phase
    # None = le maître du jeu (le moteur) est l'auteur.
    author_id: Optional[str] = None
    # Texte rédigé par le moteur. Il ne doit contenir que ce que les lecteurs ont le droit de savoir.
    content: str = Field(min_length=1)
    visible_to: Optional[frozenset[str]] = None

    def is_visible_to(self, player_id: str) -> bool:
        if self.visible_to is None:
            return True
        return player_id in self.visible_to