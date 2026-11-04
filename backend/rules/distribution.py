import random

from backend.models import Alignement, Role
from backend.rules.catalogue import SIX_PLAYER_ROLES, get_role


def distribute_roles(ids: list[str], rng: random.Random) -> dict[str, Role]:
    """Attribue au hasard un rôle de la partie à chaque joueur, un seul par joueur."""
    if len(ids) != len(SIX_PLAYER_ROLES):
        raise ValueError(f"il faut {len(SIX_PLAYER_ROLES)} joueurs, reçu {len(ids)}")
    if len(set(ids)) != len(ids):
        raise ValueError("identifiants de joueurs en double")
    names = list(SIX_PLAYER_ROLES)
    rng.shuffle(names)
    return {player_id: get_role(name) for player_id, name in zip(ids, names)}


def choose_false_lead(roles: dict[str, Role], rng: random.Random) -> str:
    """Choisit au hasard le joueur du bien qui apparaîtra comme démon à la Voyante.
    La Voyante ne peut pas être sa propre fausse piste, et le vrai démon n'est jamais choisi."""
    candidates = sorted(
        player_id
        for player_id, role in roles.items()
        if role.alignment == Alignement.BON and role.name_EN != "psychic"
    )
    if not candidates:
        raise ValueError("aucun joueur du bien éligible pour la fausse piste")
    return rng.choice(candidates)