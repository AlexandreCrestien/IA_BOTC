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
        if game_master in player_ids:
            raise ValueError(f"'{game_master}' est réservé au Maître du Jeu, pas à un joueur")
        self.player_ids = frozenset(player_ids)
        self._events: list[Event] = []
        # Moment actuel de la partie : la partie commence par la nuit 1
        self.day = 1
        self.phase = Phase.night

    def advance_phase(self) -> None:
        """Nuit N -> Jour N -> Nuit N+1. Appelé par l'orchestrateur à chaque changement de phase."""
        if self.phase == Phase.night:
            self.phase = Phase.day
        else:
            self.phase = Phase.night
            self.day += 1

    def _check_readers(self, visible_to: frozenset[str] | None) -> None:
        if visible_to is None:
            return
        if not visible_to:
            raise ValueError("Un événement doit être visible par au moins un joueur")
        unknown = visible_to - self.player_ids
        if unknown:
            raise ValueError(f"Joueurs inconnus dans visible_to : {sorted(unknown)}")

    def _check_author(self, author: str) -> None:
        if author != game_master and author not in self.player_ids:
            raise ValueError(f"Auteur inconnu : {author}")

    def add_event(self, type: EventType, author: str, content: str, visible_to: set[str] | None) -> Event:
        """Valide et enregistre un événement au moment actuel de la partie.

        Si l'auteur est un joueur, il est ajouté automatiquement aux lecteurs.
        """
        self._check_author(author)
        if visible_to is not None:
            visible_to = frozenset(visible_to)
            self._check_readers(visible_to)
            if author != game_master:
                visible_to = visible_to | {author}
        event = Event(day=self.day, phase=self.phase, type=type, author=author,
                      content=content, visible_to=visible_to)
        self._events.append(event)
        return event

    def add_public(self, type: EventType, author: str, content: str) -> Event:
        """Visible par tous : annonce, mort, salon public, nomination, vote, "A et B ont discuté"."""
        return self.add_event(type, author, content, visible_to=None)

    def add_private(self, type: EventType, author: str, content: str, participants: set[str]) -> Event:
        """Visible par un groupe : résumé de conversation privée, alliés entre démons."""
        return self.add_event(type, author, content, visible_to=participants)

    def add_personal(self, type: EventType, author: str, content: str, player: str) -> Event:
        """Visible par un seul joueur : action de nuit, information de nuit, rôle."""
        return self.add_event(type, author, content, visible_to={player})
