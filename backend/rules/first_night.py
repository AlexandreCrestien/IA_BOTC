import random
from typing import NamedTuple

from backend.models import Team, GameState, RoleKey, EffectType


class FirstNightInfo(NamedTuple):
    """Information donnée en début de partie.
    kind = 'demon' : le complice voit le démon.
    kind = 'accomplice' : le démon voit le complice.
    kind = 'pair' : l'Inquisiteur voit un complice parmi deux joueurs (fausse info s'il est empoisonné)."""
    viewer_id: str
    kind: str
    subject_ids: tuple[str, ...]


def first_night_info(state: GameState, rng: random.Random) -> list[FirstNightInfo]:
    demons = [p for p in state.players if p.role.team == Team.DEMON]
    minions = [p for p in state.players if p.role.team == Team.ACCOMPLICE]
    if len(demons) != 1 or len(minions) != 1:
        raise ValueError("il faut exactement un démon et un complice")
    demon, accomplice = demons[0], minions[0]

    infos = [
        FirstNightInfo(accomplice.id, "demon", (demon.id,)),
        FirstNightInfo(demon.id, "accomplice", (accomplice.id,)),
    ]
    for inquisitor in (p for p in state.players if p.role.name_EN == RoleKey.INQUISITOR):
        if inquisitor.has_effect(EffectType.POISONED):
            # Information fausse : deux autres joueurs tirés au hasard, sans garantie de complice.
            others = [p.id for p in state.players if p.id != inquisitor.id]
            pair = rng.sample(others, 2)
        else:
            candidates = [p.id for p in state.players if p.id not in (inquisitor.id, accomplice.id)]
            pair = [accomplice.id, rng.choice(candidates)]
            rng.shuffle(pair)
        infos.append(FirstNightInfo(inquisitor.id, "pair", tuple(pair)))
    return infos