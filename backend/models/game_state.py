from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.channel import Channel
from backend.models.enums import Phase
from backend.models.game_event import GameEvent
from backend.models.player import Player


class GameState(BaseModel):
    """Conteneur de toute la partie. Ne contient aucune règle : les règles vivent dans rules."""

    model_config = ConfigDict(frozen=True)

    turn: int = Field(default=1, ge=1)
    phase: Phase = Phase.NUIT
    players: tuple[Player, ...] = ()
    channels: tuple[Channel, ...] = ()
    log: tuple[GameEvent, ...] = ()

    @model_validator(mode="after")
    def _check_unique_ids(self):
        player_ids = [p.id for p in self.players]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("identifiants de joueurs en double")
        channel_ids = [c.id for c in self.channels]
        if len(channel_ids) != len(set(channel_ids)):
            raise ValueError("identifiants de salons en double")
        return self

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(f"joueur inconnu : {player_id}")

    def channel(self, channel_id: str) -> Channel:
        for c in self.channels:
            if c.id == channel_id:
                return c
        raise KeyError(f"salon inconnu : {channel_id}")

    def alive_players(self) -> tuple[Player, ...]:
        return tuple(p for p in self.players if p.alive)

    def replace_player(self, player: Player) -> "GameState":
        self.player(player.id)  # erreur si le joueur n'existe pas
        return self.model_copy(
            update={"players": tuple(player if p.id == player.id else p for p in self.players)}
        )

    def replace_channel(self, channel: Channel) -> "GameState":
        self.channel(channel.id)  # erreur si le salon n'existe pas
        return self.model_copy(
            update={"channels": tuple(channel if c.id == channel.id else c for c in self.channels)}
        )

    def add_event(self, event: GameEvent) -> "GameState":
        return self.model_copy(update={"log": self.log + (event,)})

    def log_visible_to(self, player_id: str) -> tuple[GameEvent, ...]:
        return tuple(e for e in self.log if e.is_visible_to(player_id))

    def next_phase(self) -> "GameState":
        """Nuit -> discussion -> vote dans le même tour ; vote -> nuit au tour suivant.
        Retire au passage les effets arrivés à leur fin, pour chaque joueur."""
        following = {Phase.NUIT: Phase.DISCUSSION, Phase.DISCUSSION: Phase.VOTE, Phase.VOTE: Phase.NUIT}
        new_phase = following[self.phase]
        new_turn = self.turn + 1 if new_phase == Phase.NUIT else self.turn
        players = tuple(p.remove_expired_effects(new_turn, new_phase) for p in self.players)
        return self.model_copy(update={"turn": new_turn, "phase": new_phase, "players": players})

    def __str__(self) -> str:
        """Résumé lisible de la partie, pour le débogage et les tests."""
        def summary(p: Player) -> str:
            effects = ", ".join(e.type.value for e in p.effects)
            return f"{p.name} ({p.role.name})" + (f" [{effects}]" if effects else "")

        alive = [summary(p) for p in self.players if p.alive]
        dead = [p.name for p in self.players if not p.alive]
        lines = [
            f"Tour {self.turn}, {self.phase.value}",
            f"Vivants ({len(alive)}) : " + (", ".join(alive) or "aucun"),
            "Morts : " + (", ".join(dead) or "aucun"),
        ]
        for c in self.channels:
            state = "ouvert" if c.open else "fermé"
            lines.append(f"Salon {c.name} ({state}, {len(c.members)} membres, {len(c.messages)} messages)")
        lines.append(f"Journal : {len(self.log)} événements")
        return "\n".join(lines)