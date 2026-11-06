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


def distribute_personalities(ids: list[str], personalities: list[dict], rng: random.Random) -> dict[str, dict]:
    """Attribue une personnalité différente à chaque joueur IA, tirée sans remise.
    ids : identifiants des joueurs IA uniquement (sans l'humain).
    personalities : données de personnalité, triées par nom pour rester reproductibles."""
    if len(ids) > len(personalities):
        raise ValueError(f"pas assez de personnalités : {len(ids)} joueurs IA, {len(personalities)} personnalités")
    ordered = sorted(personalities, key=lambda p: p["personality_name_EN"])
    chosen = rng.sample(ordered, len(ids))
    return dict(zip(ids, chosen))


def assign_players(
    names: dict[str, str],
    human_id: str,
    personality_names: list[str],
    rng: random.Random,
) -> dict[str, tuple[str, dict, dict | None]]:
    """Relie rôles et personnalités aux joueurs, au format attendu par create_all_agents.
    names : {id_joueur: nom_affiché}. L'humain reçoit un rôle mais aucune personnalité."""
    if human_id not in names:
        raise ValueError(f"l'humain {human_id} n'est pas dans la liste des joueurs")
    if len(set(names.values())) != len(names):
        raise ValueError("noms de joueurs en double")
    ids = list(names)
    roles = distribute_roles(ids, rng)
    ai_ids = [player_id for player_id in ids if player_id != human_id]
    personalities = distribute_personalities(
        ai_ids,
        [{"personality_name_EN": n, "personality_name_FR": n} for n in personality_names],
        rng,
    )
    assignments = {}
    for player_id in ids:
        role_data = roles[player_id].model_dump()
        personality_data = personalities.get(player_id)
        assignments[player_id] = (names[player_id], role_data, personality_data)
    return assignments