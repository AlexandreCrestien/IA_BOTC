"""Partie réelle avec les IA, pour voir leurs réponses et repérer les problèmes.
Lancement manuel : python scripts/play_real_game.py
Nécessite les clés d'API dans .env et fait de vrais appels (coût et lenteur)."""
import asyncio
import logging
import os
import random
import sys
from pathlib import Path

# Doit être fait avant l'import de litellm (via backend.ai_turns) pour réduire son bruit.
os.environ.setdefault("LITELLM_LOG", "ERROR")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import litellm  # noqa: E402

from backend.ai_turns import play_turn_with_ai  # noqa: E402
from backend.game_engine import setup_game  # noqa: E402
from backend.models import EventType  # noqa: E402

litellm.suppress_debug_info = True

NAMES = {"h": "moi", "p1": "marIA", "p2": "tobIAs", "p3": "mAIsie", "p4": "adrIAn", "p5": "dIAne"}
HUMAN_ID = "h"  # pas d'agent : reçoit un choix aléatoire pour l'instant
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]
MAX_TURNS = 5

# Les logs de LiteLLM (routeur, fallbacks, cooldowns) noient la partie : on ne garde que les avertissements.
LITELLM_LOGGERS = ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy")


def label(state, player_id):
    if player_id is None:
        return "personne"
    return state.player(player_id).name


async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s : %(message)s")
    for name in LITELLM_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    rng = random.Random()
    state, agents, memory = setup_game(NAMES, HUMAN_ID, PERSONALITIES, rng)

    print("\n=== Rôles (visibles pour toi, pas pour les IA) ===")
    for player in state.players:
        print(f"  {player.name} : {player.role.name_FR}")

    already_shown = 0
    for _ in range(MAX_TURNS):
        print(f"\n=== Tour {state.turn} ===")
        result = await play_turn_with_ai(state, rng, agents, memory)

        messages = [e for e in memory.events_for(HUMAN_ID) if e.type == EventType.public_message]
        print("-- Discussion --")
        for event in messages[already_shown:]:
            print(f"  {memory.name_of(event.author_id)} : {event.content}")
        already_shown = len(messages)

        print("-- Choix de nuit --")
        for player_id, targets in result.night_choices.items():
            player = state.player(player_id)
            cibles = ", ".join(label(state, t) for t in targets) or "personne"
            print(f"  {player.name} ({player.role.name_FR}) -> {cibles}")

        print("-- Votes --")
        for player_id, target in result.votes.items():
            print(f"  {state.player(player_id).name} -> {label(state, target)}")

        morts = ", ".join(label(state, p) for p in result.night_deaths) or "personne"
        print(f"-- Morts de la nuit : {morts}")
        print(f"-- Exécuté : {label(state, result.executed)}")

        state = result.state
        if result.game_winner is not None:
            print(f"\n=== Fin de partie : victoire {result.game_winner.value} ===")
            return
    print("\n=== Arrêt après le nombre maximum de tours ===")


if __name__ == "__main__":
    asyncio.run(main())