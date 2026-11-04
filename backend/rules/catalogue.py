from backend.models import Equipe, Phase, Role, TypeEffet

# Catalogue des rôles de la partie. La clé correspond au fichier skills/roles/<clé>.md.
# Pour ajouter un rôle, on ajoute une entrée ici, avec son test.
ROLES: dict[str, Role] = {
    "imp": Role(
        name="imp",
        team=Equipe.DEMON,
        phase=Phase.NUIT,
        effects=(TypeEffet.TUE,),
        description="Chaque nuit, choisit un habitant à tuer.",
    ),
    "poisoner": Role(
        name="poisoner",
        team=Equipe.SBIRE,
        phase=Phase.NUIT,
        effects=(TypeEffet.EMPOISONNE,),
        description="Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante.",
    ),
    "monk": Role(
        name="monk",
        team=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effects=(TypeEffet.PROTEGE,),
        description="Chaque nuit, protège un habitant de l'attaque du diablotin.",
    ),
    "psychic": Role(
        name="psychic",
        team=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effects=(TypeEffet.SONDE,),
        allowed_links=("fausse_piste",),
        description="Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie.",
    ),
    "detective": Role(
        name="detective",
        team=Equipe.VILLAGEOIS,
        phase=None,
        effects=(TypeEffet.SONDE,),
        description="Au début de la partie, voit un sbire parmi deux joueurs, dont l'un est choisi au hasard.",
    ),
    "butler": Role(
        name="butler",
        team=Equipe.OUTSIDER,
        phase=Phase.NUIT,
        effects=(),
        allowed_links=("maitre",),
        description="Chaque nuit, choisit un maître. Ne peut voter que si son maître vote aussi.",
    ),
}


def get_role(name: str) -> Role:
    """Renvoie la fiche d'un rôle du catalogue. Erreur claire si le rôle est inconnu."""
    if name not in ROLES:
        raise KeyError(f"rôle inconnu : {name}")
    return ROLES[name]


# Rôles d'une partie à six joueurs : un seul de chaque, attribué au hasard.
SIX_PLAYER_ROLES = ("imp", "poisoner", "monk", "psychic", "detective", "butler")