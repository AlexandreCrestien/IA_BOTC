from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import Alignement, Equipe, Phase, RoleKey

# Camps du côté du bien. L'outsider est villageois, donc du côté du bien.
GOOD_TEAMS = {Equipe.VILLAGEOIS, Equipe.OUTSIDER}


class Role(BaseModel):
    """Fiche de règles, identique pour tous les joueurs qui ont ce rôle.
    Ne contient aucun état de partie : la vie, le pouvoir utilisé ou les effets
    appartiennent au joueur, pas au rôle."""

    model_config = ConfigDict(frozen=True)

    name_FR: str = Field(min_length=1)
    name_EN: RoleKey
    team: Equipe
    # None = le rôle n'agit à aucun moment précis.
    phase: Optional[Phase] = None
    # Action de nuit : nombre de cibles à choisir, et si le joueur peut se choisir lui-même.
    night_targets: int = Field(default=1, ge=1)
    can_target_self: bool = False
    # Clés de lien que ce rôle a le droit de poser sur un joueur.
    allowed_links: tuple[str, ...] = ()
    # Texte affiché au joueur et repris par le skill de l'agent.
    description: str = ""

    @property
    def alignment(self) -> Alignement:
        return Alignement.BON if self.team in GOOD_TEAMS else Alignement.MAUVAIS