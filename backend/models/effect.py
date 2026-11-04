from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from backend.models.clock import instant
from backend.models.enums import Phase, TypeEffet


class Effect(BaseModel):
    """Effet actif sur un joueur, avec son début et sa fin.
    Immutable : tout changement produit un nouvel objet Effect.
    Fin None et None = effet permanent."""

    model_config = ConfigDict(frozen=True)

    type: TypeEffet
    source: str  # rôle ou événement qui a créé l'effet
    turn_start: int
    phase_start: Phase
    turn_end: Optional[int] = None
    phase_end: Optional[Phase] = None

    @model_validator(mode="after")
    def _check_end_is_coherent(self):
        if (self.turn_end is None) != (self.phase_end is None):
            raise ValueError("tour_fin et phase_fin doivent être tous deux renseignés, ou tous deux absents")
        if self.turn_end is not None and instant(self.turn_end, self.phase_end) <= instant(self.turn_start, self.phase_start):
            raise ValueError("la fin d'un effet doit être postérieure à son début")
        return self

    def is_expired(self, turn: int, phase: Phase) -> bool:
        """Vrai si l'effet doit être retiré à ce moment de la partie."""
        if self.turn_end is None:
            return False
        return instant(turn, phase) >= instant(self.turn_end, self.phase_end)