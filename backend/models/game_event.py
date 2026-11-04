from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import Phase


class GameEvent(BaseModel):
    """Une ligne du journal de la partie.
    public=True : visible de tous. public=False : visible seulement des destinataires.
    public=False sans destinataire : visible du moteur seul."""

    model_config = ConfigDict(frozen=True)

    type: str = Field(min_length=1)
    turn: int
    phase: Phase
    public: bool = True
    recipients: tuple[str, ...] = ()

    def is_visible_to(self, player_id: str) -> bool:
        return self.public or player_id in self.recipients