from backend.models import Team, Phase, Role, RoleKey

# Catalogue des rôles de la partie. La clé correspond au fichier skills/roles/<clé>.md.
# Pour ajouter un rôle, on ajoute une entrée ici, avec son test.
ROLES: dict[RoleKey, Role] = {
    RoleKey.REAPER: Role(
        name_FR="Faucheur",
        name_EN=RoleKey.REAPER,
        team=Team.DEMON,
        phase=Phase.NIGHT,
        description="Chaque nuit, choisit un habitant à tuer.",
    ),
    RoleKey.APOTHECARY: Role(
        name_FR="Apothicaire",
        name_EN=RoleKey.APOTHECARY,
        team=Team.ACCOMPLICE,
        phase=Phase.NIGHT,
        description="Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante.",
    ),
    RoleKey.WATCHMAN: Role(
        name_FR="Veilleur",
        name_EN=RoleKey.WATCHMAN,
        team=Team.TOWNSFOLK,
        phase=Phase.NIGHT,
        description="Chaque nuit, protège un habitant de l'attaque du Faucheur.",
    ),
    RoleKey.MEDIUM: Role(
        name_FR="Médium",
        name_EN=RoleKey.MEDIUM,
        team=Team.TOWNSFOLK,
        phase=Phase.NIGHT,
        night_targets=2,
        can_target_self=True,
        allowed_links=("false_lead",),
        description="Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie.",
    ),
    RoleKey.INQUISITOR: Role(
        name_FR="Inquisiteur",
        name_EN=RoleKey.INQUISITOR,
        team=Team.TOWNSFOLK,
        phase=None,
        description="Au début de la partie, voit un complice parmi deux joueurs, dont l'un est choisi au hasard.",
    ),
    RoleKey.VALET: Role(
        name_FR="Valet",
        name_EN=RoleKey.VALET,
        team=Team.OUTCAST,
        phase=Phase.NIGHT,
        allowed_links=("master",),
        description="Chaque nuit, choisit un maître. Ne peut voter que si son maître vote aussi.",
    ),
}


def get_role(name: str) -> Role:
    """Renvoie la fiche d'un rôle du catalogue (clé ou chaîne équivalente). Erreur claire si le rôle est inconnu."""
    if name not in ROLES:
        raise KeyError(f"rôle inconnu : {name}")
    return ROLES[RoleKey(name)]


# Rôles d'une partie à six joueurs : un seul de chaque, attribué au hasard.
SIX_PLAYER_ROLES = (RoleKey.REAPER, RoleKey.APOTHECARY, RoleKey.WATCHMAN, RoleKey.MEDIUM, RoleKey.INQUISITOR,
                    RoleKey.VALET)