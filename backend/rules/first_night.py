import random
from typing import NamedTuple

from backend.models import Equipe, GameState, TypeEffet


class FirstNightInfo(NamedTuple):
    """Information donnée en début de partie.
    kind = 'demon' : le sbire voit le démon.
    kind = 'minion' : le démon voit le sbire.
    kind = 'pair' : le Détective voit un sbire parmi deux joueurs (fausse info s'il est empoisonné)."""
    viewer_id: str
    kind: str
    subject_ids: tuple[str, ...]


def first_night_info(state: GameState, rng: random.Random) -> list[FirstNightInfo]:
    demons = [p for p in state.players if p.role.team == Equipe.DEMON]
    minions = [p for p in state.players if p.role.team == Equipe.SBIRE]
    if len(demons) != 1 or len(minions) != 1:
        raise ValueError("il faut exactement un démon et un sbire")
    demon, minion = demons[0], minions[0]

    infos = [
        FirstNightInfo(minion.id, "demon", (demon.id,)),
        FirstNightInfo(demon.id, "minion", (minion.id,)),
    ]
    for detective in (p for p in state.players if p.role.name == "detective"):
        if detective.has_effect(TypeEffet.EMPOISONNE):
            # Information fausse : deux autres joueurs tirés au hasard, sans garantie de sbire.
            others = [p.id for p in state.players if p.id != detective.id]
            pair = rng.sample(others, 2)
        else:
            candidates = [p.id for p in state.players if p.id not in (detective.id, minion.id)]
            pair = [minion.id, rng.choice(candidates)]
            rng.shuffle(pair)
        infos.append(FirstNightInfo(detective.id, "pair", tuple(pair)))
    return infos