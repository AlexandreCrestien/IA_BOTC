from typing import Optional

from backend.models import Alignment, Team, GameState


def winner(state: GameState) -> Optional[Alignment]:
    """Camp gagnant, ou None si la partie continue.
    Le bien gagne si le Faucheur meurt. Le mal gagne s'il ne reste aucun joueur du bien vivant.
    Si les deux conditions sont vraies en même temps, le bien l'emporte."""
    demon_alive = any(p.alive for p in state.players if p.role.team == Team.DEMON)
    if not demon_alive:
        return Alignment.GOOD
    good_alive = any(p.alive for p in state.players if p.role.alignment == Alignment.GOOD)
    if not good_alive:
        return Alignment.EVIL
    return None