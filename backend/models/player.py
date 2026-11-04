from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.effect import Effect
from backend.models.enums import Phase, TypeEffet
from backend.models.role import Role


class Player(BaseModel):
    """État d'une personne dans la partie. Immutable.
    Ne contient que l'état du joueur. La fiche de règles reste dans Role."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: Role
    alive: bool = True
    # Pouvoir déjà utilisé. La remise à zéro éventuelle est gérée par le moteur.
    power_used: bool = False
    # Un joueur mort garde une seule voix pour le reste de la partie.
    ghost_vote: bool = False
    effects: tuple[Effect, ...] = ()
    # Liens vers d'autres joueurs (ex. "maitre", "fausse_piste"). Les clés autorisées sont dans la fiche du rôle.
    links: dict[str, str] = Field(default_factory=dict)

    @property
    def can_act(self) -> bool:
        """Vrai si le joueur a encore un pouvoir disponible. La phase est vérifiée par le moteur."""
        return self.alive and self.role.phase is not None and not self.power_used

    @property
    def can_vote(self) -> bool:
        return self.alive or self.ghost_vote

    def has_effect(self, effect_type: TypeEffet) -> bool:
        return any(e.type == effect_type for e in self.effects)

    def add_effect(self, effect: Effect) -> "Player":
        return self.model_copy(update={"effects": self.effects + (effect,)})

    def remove_expired_effects(self, turn: int, phase: Phase) -> "Player":
        remaining = tuple(e for e in self.effects if not e.is_expired(turn, phase))
        return self.model_copy(update={"effects": remaining})

    def die(self) -> "Player":
        if not self.alive:
            raise ValueError(f"{self.name} est déjà mort")
        return self.model_copy(update={"alive": False, "ghost_vote": True})

    def use_ghost_vote(self) -> "Player":
        if self.alive or not self.ghost_vote:
            raise ValueError(f"{self.name} n'a pas de vote fantôme à utiliser")
        return self.model_copy(update={"ghost_vote": False})

    def link(self, key: str) -> Optional[str]:
        return self.links.get(key)

    def with_link(self, key: str, target_id: str) -> "Player":
        """Stocke un lien. Aucune règle ici : elles sont vérifiées par le moteur."""
        return self.model_copy(update={"links": {**self.links, key: target_id}})