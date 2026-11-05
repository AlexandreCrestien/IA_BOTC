from typing import Optional

from backend.models import Alignement, Equipe, GameState


def winner(state: GameState) -> Optional[Alignement]:
    """Camp gagnant, ou None si la partie continue.
    Le bien gagne si le Diablotin meurt. Le mal gagne s'il ne reste aucun joueur du bien vivant.
    Si les deux conditions sont vraies en même temps, le bien l'emporte."""
    demon_alive = any(p.alive for p in state.players if p.role.team == Equipe.DEMON)
    if not demon_alive:
        return Alignement.BON
    good_alive = any(p.alive for p in state.players if p.role.alignment == Alignement.BON)
    if not good_alive:
        return Alignement.MAUVAIS
    return None