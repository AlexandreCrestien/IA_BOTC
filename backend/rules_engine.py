from backend.models import Alignement, Equipe, Joueur, Phase, Role, TypeEffet

# Catalogue des rôles de la partie. Chaque entrée est une fiche de règles.
# Pour ajouter un rôle, on ajoute une entrée ici, avec son test.
ROLES: dict[str, Role] = {
    "Diablotin": Role(
        nom="Diablotin",
        camp=Equipe.DEMON,
        phase=Phase.NUIT,
        effets=(TypeEffet.TUE,),
        description="Chaque nuit, choisit un habitant à tuer.",
    ),
    "Empoisonneur": Role(
        nom="Empoisonneur",
        camp=Equipe.SBIRE,
        phase=Phase.NUIT,
        effets=(TypeEffet.EMPOISONNE,),
        description="Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante.",
    ),
    "Moine": Role(
        nom="Moine",
        camp=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effets=(TypeEffet.PROTEGE,),
        description="Chaque nuit, protège un habitant de l'attaque du diablotin.",
    ),
    "Voyante": Role(
        nom="Voyante",
        camp=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effets=(TypeEffet.SONDE,),
        description="Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie.",
    ),
    "Détective": Role(
        nom="Détective",
        camp=Equipe.VILLAGEOIS,
        phase=None,
        effets=(TypeEffet.SONDE,),
        description="Au début de la partie, voit un sbire parmi deux joueurs, dont l'un est choisi au hasard.",
    ),
    "Majordome": Role(
        nom="Majordome",
        camp=Equipe.OUTSIDER,
        phase=Phase.NUIT,
        effets=(),
        description="Chaque nuit, choisit un maître. Ne peut voter que si son maître vote aussi.",
    ),
}


def obtenir_role(nom: str) -> Role:
    """Renvoie la fiche d'un rôle du catalogue. Erreur claire si le rôle est inconnu."""
    if nom not in ROLES:
        raise KeyError(f"rôle inconnu : {nom}")
    return ROLES[nom]


import random

from backend.models import Alignement, Equipe, Phase, Role, TypeEffet

# Catalogue des rôles de la partie. Chaque entrée est une fiche de règles.
# Pour ajouter un rôle, on ajoute une entrée ici, avec son test.
ROLES: dict[str, Role] = {
    "Diablotin": Role(
        nom="Diablotin",
        camp=Equipe.DEMON,
        phase=Phase.NUIT,
        effets=(TypeEffet.TUE,),
        description="Chaque nuit, choisit un habitant à tuer.",
    ),
    "Empoisonneur": Role(
        nom="Empoisonneur",
        camp=Equipe.SBIRE,
        phase=Phase.NUIT,
        effets=(TypeEffet.EMPOISONNE,),
        description="Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante.",
    ),
    "Moine": Role(
        nom="Moine",
        camp=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effets=(TypeEffet.PROTEGE,),
        description="Chaque nuit, protège un habitant de l'attaque du diablotin.",
    ),
    "Voyante": Role(
        nom="Voyante",
        camp=Equipe.VILLAGEOIS,
        phase=Phase.NUIT,
        effets=(TypeEffet.SONDE,),
        liens_autorises=("fausse_piste",),
        description="Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie.",
    ),
    "Détective": Role(
        nom="Détective",
        camp=Equipe.VILLAGEOIS,
        phase=None,
        effets=(TypeEffet.SONDE,),
        description="Au début de la partie, voit un sbire parmi deux joueurs, dont l'un est choisi au hasard.",
    ),
    "Majordome": Role(
        nom="Majordome",
        camp=Equipe.OUTSIDER,
        phase=Phase.NUIT,
        effets=(),
        liens_autorises=("maitre",),
        description="Chaque nuit, choisit un maître. Ne peut voter que si son maître vote aussi.",
    ),
}


def obtenir_role(nom: str) -> Role:
    """Renvoie la fiche d'un rôle du catalogue. Erreur claire si le rôle est inconnu."""
    if nom not in ROLES:
        raise KeyError(f"rôle inconnu : {nom}")
    return ROLES[nom]


# Rôles d'une partie à six joueurs : un seul de chaque, attribué au hasard.
ROLES_PARTIE_6 = ("Diablotin", "Empoisonneur", "Moine", "Voyante", "Détective", "Majordome")


def distribuer_roles(ids: list[str], rng: random.Random) -> dict[str, Role]:
    """Attribue au hasard un rôle de la partie à chaque joueur, un seul par joueur."""
    if len(ids) != len(ROLES_PARTIE_6):
        raise ValueError(f"il faut {len(ROLES_PARTIE_6)} joueurs, reçu {len(ids)}")
    if len(set(ids)) != len(ids):
        raise ValueError("identifiants de joueurs en double")
    noms = list(ROLES_PARTIE_6)
    rng.shuffle(noms)
    return {joueur_id: obtenir_role(nom) for joueur_id, nom in zip(ids, noms)}


def choisir_fausse_piste(roles: dict[str, Role], rng: random.Random) -> str:
    """Choisit au hasard le joueur du bien qui apparaîtra comme démon à la Voyante.
    La Voyante ne peut pas être sa propre fausse piste, et le vrai démon n'est jamais choisi."""
    candidats = sorted(
        jid for jid, r in roles.items() if r.alignement == Alignement.BON and r.nom != "Voyante"
    )
    if not candidats:
        raise ValueError("aucun joueur du bien éligible pour la fausse piste")
    return rng.choice(candidats)

def definir_lien(joueur: Joueur, cle: str, cible_id: str) -> Joueur:
    """Pose un lien si le rôle a le droit de l'utiliser, vers une autre personne."""
    if cle not in joueur.role.liens_autorises:
        raise ValueError(f"le rôle {joueur.role.nom} ne peut pas poser de lien « {cle} »")
    if cible_id == joueur.id:
        raise ValueError("un joueur ne peut pas se désigner lui-même")
    return joueur.avec_lien(cle, cible_id)