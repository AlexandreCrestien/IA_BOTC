from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import Phase


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    author_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    turn: int
    phase: Phase


class Channel(BaseModel):
    """Conversation publique ou privée. L'historique n'est jamais supprimé.
    Un salon fermé reste lisible, mais n'accepte plus de messages."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    public: bool = False
    members: tuple[str, ...] = Field(min_length=1)
    messages: tuple[Message, ...] = ()
    open: bool = True

    def is_member(self, player_id: str) -> bool:
        return player_id in self.members

    def messages_visible_to(self, player_id: str) -> tuple[Message, ...]:
        return self.messages if self.is_member(player_id) else ()

    def add_member(self, player_id: str) -> "Channel":
        if not self.open:
            raise ValueError(f"le salon {self.name} est fermé")
        if self.is_member(player_id):
            raise ValueError(f"{player_id} est déjà membre de {self.name}")
        return self.model_copy(update={"members": self.members + (player_id,)})

    def add_message(self, message: Message) -> "Channel":
        if not self.open:
            raise ValueError(f"le salon {self.name} est fermé")
        if not self.is_member(message.author_id):
            raise ValueError(f"{message.author_id} n'est pas membre de {self.name}")
        return self.model_copy(update={"messages": self.messages + (message,)})

    def close(self) -> "Channel":
        if not self.open:
            raise ValueError(f"le salon {self.name} est déjà fermé")
        return self.model_copy(update={"open": False})