from backend.models import Equipe, Phase, Role, TypeEffet

# Catalogue des rôles de la partie. Chaque entrée est une fiche de règles.
# Pour ajouter un rôle, on ajoute une entrée ici, avec son test.
ROLES: dict[str, Role] = {
    "Diablotin": Role(
        name="Diablotin",
        team=Equipe.DEMON,
        phase=Phase.NUIT,
        effects=(TypeEffet.TUE,),
        description="Chaque nuit, choisit un habitant à tuer.",
    ),
    "Empoisonneur": Role(
        name="Empoisonneur",
        team=Equipe.SBIRE,
        phase=Phase.NUIT,
        effects=(TypeEffet.EMPOISONNE,),
        description="Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante.",
    ),
    "Moine": Role(
        name="Moine",
        team=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effects=(TypeEffet.PROTEGE,),
        description="Chaque nuit, protège un habitant de l'attaque du diablotin.",
    ),
    "Voyante": Role(
        name="Voyante",
        team=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effects=(TypeEffet.SONDE,),
        allowed_links=("fausse_piste",),
        description="Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie.",
    ),
    "Détective": Role(
        name="Détective",
        team=Equipe.VILLAGEOIS,
        phase=None,
        effects=(TypeEffet.SONDE,),
        description="Au début de la partie, voit un sbire parmi deux joueurs, dont l'un est choisi au hasard.",
    ),
    "Majordome": Role(
        name="Majordome",
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
SIX_PLAYER_ROLES = ("Diablotin", "Empoisonneur", "Moine", "Voyante", "Détective", "Majordome")