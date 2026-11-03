from enum import StrEnum
from pydantic import BaseModel, ConfigDict

game_master = "game_master"

class Phase(StrEnum):
    night = "night"
    day = "day"

class EventType(StrEnum):
    announcement = "announcement"    # annonce du Maître du Jeu (public)
    death = "death"            # mort ou exécution (public)
    public_message = "public_message"   # message dans le salon public (public)
    private_meeting ="private_meeting"  # "A et B ont discuté en privé", sans le contenu (public)
    private_summary = "private_summary"  # contenu / résumé d'une conversation privée (participants)
    nomination = "nomination"       # un joueur en désigne un autre (public)
    vote = "vote"             # vote d'un joueur (public, à confirmer avec l'équipe)
    night_action = "night_action"     # cible choisie par un joueur la nuit (lui seul)
    night_info = "night_info"       # information reçue la nuit : Voyante, Détective... (lui seul)
    role_info = "role_info"        # rôle et éventuels alliés donnés au début (lui seul ou les démons)


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    day: int
    phase: Phase
    type: EventType
    author: str                          # id d'un joueur ou game master
    content: str
    visible_to: frozenset[str] | None    # None = tout le monde


class MemoryManager:
    def __init__(self, player_ids: list[str]):
        duplicates = sorted({p for p in player_ids if player_ids.count(p) > 1})
        if duplicates:
            raise ValueError(f"Identifiants de joueurs en double : {duplicates}")
        self.player_ids = frozenset(player_ids)
        self._events: list[Event] = []

    def _check_readers(self, visible_to: frozenset[str] | None) -> None:
        if visible_to is None:
            return
        if not visible_to:
            raise ValueError("Un événement doit être visible par au moins un joueur")
        unknown = visible_to - self.player_ids
        if unknown:
            raise ValueError(f"Joueurs inconnus dans visible_to : {sorted(unknown)}")
