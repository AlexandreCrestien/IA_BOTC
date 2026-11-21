"""Partie réelle avec les IA, pour voir leurs réponses et repérer les problèmes.
Lancement manuel : python scripts/play_ai_game.py
Nécessite les clés d'API dans .env et fait de vrais appels (coût et lenteur)."""
import asyncio
import logging
import os
import random
import sys
from pathlib import Path

# Doit être fait avant l'import de litellm (via backend.ai.choices) pour réduire son bruit.
os.environ.setdefault("LITELLM_LOG", "ERROR")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import litellm  # noqa: E402

from backend.engine.config import AI_NAMES, PERSONALITY_NAMES  # noqa: E402
from backend.engine.setup import setup_game  # noqa: E402
from backend.engine.human_port import AutoHumanPort  # noqa: E402
from backend.models import EventType  # noqa: E402
from backend.engine.turn import play_turn  # noqa: E402

litellm.suppress_debug_info = True

NAMES = {"h": "alex", **AI_NAMES}
HUMAN_ID = "h"  # sans agent : joueur automatique (choix de nuit au hasard, abstention, jamais de message)
PERSONALITIES = PERSONALITY_NAMES
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
        result = await play_turn(state, rng, agents, memory, HUMAN_ID, AutoHumanPort())

        messages = [e for e in memory.events_for(HUMAN_ID) if e.type == EventType.PUBLIC_MESSAGE]
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