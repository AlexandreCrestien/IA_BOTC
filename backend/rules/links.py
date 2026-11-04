from backend.models import Player


def set_link(player: Player, key: str, target_id: str) -> Player:
    """Pose un lien si le rôle a le droit de l'utiliser, vers une autre personne."""
    if key not in player.role.allowed_links:
        raise ValueError(f"le rôle {player.role.name} ne peut pas poser de lien « {key} »")
    if target_id == player.id:
        raise ValueError("un joueur ne peut pas se désigner lui-même")
    return player.with_link(key, target_id)