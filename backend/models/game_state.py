from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.enums import Phase
from backend.models.player import Player


class GameState(BaseModel):
    """Conteneur de toute la partie. Ne contient aucune règle : les règles vivent dans rules."""

    model_config = ConfigDict(frozen=True)

    turn: int = Field(default=1, ge=1)
    phase: Phase = Phase.NUIT
    players: tuple[Player, ...] = ()

    @model_validator(mode="after")
    def _check_unique_ids(self):
        player_ids = [p.id for p in self.players]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("identifiants de joueurs en double")
        return self

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(f"joueur inconnu : {player_id}")

    def alive_players(self) -> tuple[Player, ...]:
        return tuple(p for p in self.players if p.alive)

    def replace_player(self, player: Player) -> "GameState":
        self.player(player.id)  # erreur si le joueur n'existe pas
        return self.model_copy(
            update={"players": tuple(player if p.id == player.id else p for p in self.players)}
        )

    def next_phase(self) -> "GameState":
        """Nuit -> discussion -> vote dans le même tour ; vote -> nuit au tour suivant.
        Au passage à la nuit : retire les effets arrivés à leur fin et remet les pouvoirs à zéro."""
        following = {Phase.NUIT: Phase.DISCUSSION, Phase.DISCUSSION: Phase.VOTE, Phase.VOTE: Phase.NUIT}
        new_phase = following[self.phase]
        new_turn = self.turn + 1 if new_phase == Phase.NUIT else self.turn
        players = tuple(p.remove_expired_effects(new_turn, new_phase) for p in self.players)
        if new_phase == Phase.NUIT:
            players = tuple(p.reset_power() for p in players)
        return self.model_copy(update={"turn": new_turn, "phase": new_phase, "players": players})

    def __str__(self) -> str:
        """Résumé lisible de la partie, pour le débogage et les tests."""
        def summary(p: Player) -> str:
            effects = ", ".join(e.type.value for e in p.effects)
            return f"{p.name} ({p.role.name_EN})" + (f" [{effects}]" if effects else "")

        alive = [summary(p) for p in self.players if p.alive]
        dead = [p.name for p in self.players if not p.alive]
        lines = [
            f"Tour {self.turn}, {self.phase.value}",
            f"Vivants ({len(alive)}) : " + (", ".join(alive) or "aucun"),
            "Morts : " + (", ".join(dead) or "aucun"),
        ]
        return "\n".join(lines)