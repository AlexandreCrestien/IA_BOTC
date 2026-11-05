from backend.models import EventType, GameEvent, Phase

Event = GameEvent  # le modèle d'événement vit maintenant dans backend.models

game_master = "game_master"


class MemoryManager:
    def __init__(self, player_ids: list[str] | dict[str, str]):
        """player_ids : liste d'ids, ou dict {id: nom affiché}.
        Avec le dict, l'historique montre les noms (ce que les agents connaissent) au lieu des ids."""
        if isinstance(player_ids, dict):
            self.names = dict(player_ids)
            player_ids = list(player_ids)
        else:
            self.names = {}
        duplicates = sorted({p for p in player_ids if player_ids.count(p) > 1})
        if duplicates:
            raise ValueError(f"Identifiants de joueurs en double : {duplicates}")
        if game_master in player_ids:
            raise ValueError(f"'{game_master}' est réservé au Maître du Jeu, pas à un joueur")
        self.player_ids = frozenset(player_ids)
        self._events: list[Event] = []
        # Moment actuel de la partie : la partie commence par la nuit 1
        self.day = 1
        self.phase = Phase.NUIT

    def advance_phase(self) -> None:
        """Nuit N -> Jour N -> Nuit N+1. Appelé par l'orchestrateur à chaque changement de phase."""
        if self.phase == Phase.NUIT:
            self.phase = Phase.DISCUSSION
        elif self.phase == Phase.DISCUSSION:
            self.phase = Phase.VOTE
        else:
            self.phase = Phase.NUIT
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
        event = Event(turn=self.day, phase=self.phase, type=type,
                      author_id=None if author == game_master else author,
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

    def events_for(self, player: str) -> list[Event]:
        """Seule façon de lire la mémoire : les événements que ce joueur a le droit de voir, dans l'ordre."""
        if player not in self.player_ids:
            raise ValueError(f"Joueur inconnu : {player}")
        return [e for e in self._events if e.visible_to is None or player in e.visible_to]

    def private_partners(self, player: str) -> set[str]:
        """Les joueurs avec qui ce joueur a déjà eu une conversation privée."""
        partners = set()
        for e in self.events_for(player):
            if e.type == EventType.private_summary:
                partners |= e.visible_to - {player}
        return partners

    def name_of(self, player: str) -> str:
        """Nom affiché d'un joueur (son id si aucun nom n'a été donné)."""
        if player == game_master:
            return "Maître du Jeu"
        return self.names.get(player, player)

    def context_for(self, player: str) -> str:
        """Texte à injecter dans le prompt de l'agent : tout ce que ce joueur sait, en français."""
        lines = []
        for e in self.events_for(player):
            moment = f"{'Nuit' if e.phase == Phase.NUIT else 'Jour'} {e.turn}"

            if e.visible_to is None:
                channel = "public"
            elif e.visible_to == {player}:
                channel = "personnel"
            else:
                others = sorted(self.name_of(p) for p in e.visible_to - {player})
                channel = f"privé avec {', '.join(others)}"

            if e.author_id is None:
                author = self.name_of(game_master)
            elif e.author_id == player:
                author = "Toi"
            else:
                author = self.name_of(e.author_id)

            lines.append(f"[{moment}] ({channel}) {author} : {e.content}")

        return "\n".join(lines) if lines else "Aucun événement pour l'instant."
