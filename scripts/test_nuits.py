"""Test de ciblage : simule 2 nuits avec les vrais agents IA, sans discussion ni vote.
Affiche le choix de chaque IA et signale les cibles mortes et les répétitions.
Environ 5 appels LLM par nuit.

Usage : python scripts/test_nuits.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import asyncio
import logging
import random

from backend.ai_turns import collect_ai_night_choices
from backend.game_engine import play_night, record_night_choices, reveal_psychic_answer, setup_game

logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
logging.getLogger("litellm").setLevel(logging.CRITICAL)

HUMAN_ID = "h"
NAMES = {"h": "alex", "p1": "marIA", "p2": "tobIAs", "p3": "mAIsie", "p4": "adrIAn", "p5": "dIAne"}
# À copier depuis tests/test_human_turns.py (même valeur que dans les tests)
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]
NIGHTS = 5
KILL_AFTER_FIRST_NIGHT = True  # tue une IA après la nuit 1, pour tester les cibles mortes
SEED = 12


async def play_night_once(state, rng, agents, memory):
    memory.set_moment(state.turn, state.phase)
    ai_night = await collect_ai_night_choices(state, agents)
    after, choices = play_night(state, rng, lambda s, pid: ai_night.get(pid, ()))
    record_night_choices(after, choices, memory)
    reveal_psychic_answer(after, choices, memory, rng)
    return after, choices


def names(state, ids):
    return ", ".join(state.player(pid).name for pid in ids) or "personne"


async def main() -> None:
    rng = random.Random(SEED)
    state, agents, memory = setup_game(NAMES, HUMAN_ID, PERSONALITIES, rng)
    print("Rôles :")
    for p in state.players:
        print(f"  {p.name} : {p.role.name_FR}")

    previous: dict[str, set[str]] = {}
    for _ in range(NIGHTS):
        print(f"\n=== Nuit {state.turn} ===")
        before = state
        state, choices = await play_night_once(state, rng, agents, memory)
        for pid, targets in choices.items():
            if pid == HUMAN_ID:
                continue
            flags = [f"cible morte : {before.player(t).name}" for t in targets if not before.player(t).alive]
            if set(targets) & previous.get(pid, set()):
                flags.append("REPÈTE la nuit précédente")
            suffix = f"  [{' ; '.join(flags)}]" if flags else ""
            print(f"  {before.player(pid).name} ({before.player(pid).role.name_FR}) -> {names(before, targets)}{suffix}")
            previous[pid] = set(targets)

        if KILL_AFTER_FIRST_NIGHT and state.turn == 1:
            victim = next(p for p in state.players if p.alive and p.id in agents)
            state = state.replace_player(victim.die())
            print(f"  (test) {victim.name} est tué à la main, pour tester les cibles mortes")

        for _ in range(3):  # NUIT -> DISCUSSION -> VOTE -> NUIT
            state = state.next_phase()

    print("\nTerminé.")


if __name__ == "__main__":
    asyncio.run(main())