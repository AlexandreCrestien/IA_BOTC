from backend.models import Equipe, Phase, Role, RoleKey

# Catalogue des rôles de la partie. La clé correspond au fichier skills/roles/<clé>.md.
# Pour ajouter un rôle, on ajoute une entrée ici, avec son test.
ROLES: dict[RoleKey, Role] = {
    RoleKey.IMP: Role(
        name_FR="Diablotin",
        name_EN=RoleKey.IMP,
        team=Equipe.DEMON,
        phase=Phase.NUIT,
        description="Chaque nuit, choisit un habitant à tuer.",
    ),
    RoleKey.POISONER: Role(
        name_FR="Empoisonneur",
        name_EN=RoleKey.POISONER,
        team=Equipe.SBIRE,
        phase=Phase.NUIT,
        description="Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante.",
    ),
    RoleKey.MONK: Role(
        name_FR="Moine",
        name_EN=RoleKey.MONK,
        team=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        description="Chaque nuit, protège un habitant de l'attaque du diablotin.",
    ),
    RoleKey.PSYCHIC: Role(
        name_FR="Voyante",
        name_EN=RoleKey.PSYCHIC,
        team=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        night_targets=2,
        can_target_self=True,
        allowed_links=("fausse_piste",),
        description="Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie.",
    ),
    RoleKey.DETECTIVE: Role(
        name_FR="Détective",
        name_EN=RoleKey.DETECTIVE,
        team=Equipe.VILLAGEOIS,
        phase=None,
        description="Au début de la partie, voit un sbire parmi deux joueurs, dont l'un est choisi au hasard.",
    ),
    RoleKey.BUTLER: Role(
        name_FR="Majordome",
        name_EN=RoleKey.BUTLER,
        team=Equipe.OUTSIDER,
        phase=Phase.NUIT,
        allowed_links=("maitre",),
        description="Chaque nuit, choisit un maître. Ne peut voter que si son maître vote aussi.",
    ),
}


def get_role(name: str) -> Role:
    """Renvoie la fiche d'un rôle du catalogue (clé ou chaîne équivalente). Erreur claire si le rôle est inconnu."""
    if name not in ROLES:
        raise KeyError(f"rôle inconnu : {name}")
    return ROLES[RoleKey(name)]


# Rôles d'une partie à six joueurs : un seul de chaque, attribué au hasard.
SIX_PLAYER_ROLES = (RoleKey.IMP, RoleKey.POISONER, RoleKey.MONK, RoleKey.PSYCHIC, RoleKey.DETECTIVE,
                    RoleKey.BUTLER)