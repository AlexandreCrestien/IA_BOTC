from typing import Optional

from backend.models import Alignment, GameState, Phase, Team


def winner(state: GameState) -> Optional[Alignment]:
    """Camp gagnant, ou None si la partie continue. Appelée après la nuit et après le vote.
    - Le bien gagne si le Faucheur meurt (prioritaire si les deux camps remplissent leur condition).
    - Le mal gagne s'il ne reste plus aucun joueur du bien en vie.
    - Après le vote, le mal gagne aussi s'il ne reste qu'un seul joueur du bien en vie : le bien n'a plus
      de vote avant la nuit, et le Faucheur le tuera. On ne joue pas cette nuit (appels LLM inutiles).
      Ce contrôle n'a pas lieu après la nuit : le dernier joueur du bien garde son vote du jour,
      avec les voix d'outre-tombe, pour tenter d'exécuter le Faucheur."""
    demon_alive = any(p.alive for p in state.players if p.role.team == Team.DEMON)
    if not demon_alive:
        return Alignment.GOOD
    good_alive = sum(1 for p in state.players if p.alive and p.role.alignment == Alignment.GOOD)
    if good_alive == 0 or (state.phase == Phase.VOTE and good_alive == 1):
        return Alignment.EVIL
    return None