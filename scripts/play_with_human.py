"""Partie avec toi comme joueur humain, dans le terminal.
Lancement : python scripts/play_with_human.py
Les IA font de vrais appels (coût et lenteur). Tu tapes tes choix quand on te les demande."""
import asyncio
import logging
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("LITELLM_LOG", "ERROR")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import litellm  # noqa: E402

from backend.game_engine import setup_game  # noqa: E402
from backend.human_turns import DayAction, play_turn_with_human  # noqa: E402
from backend.rules import legal_actions  # noqa: E402

litellm.suppress_debug_info = True

NAMES = {"h": "moi", "p1": "marIA", "p2": "tobIAs", "p3": "mAIsie", "p4": "adrIAn", "p5": "dIAne"}
HUMAN_ID = "h"
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]
MAX_TURNS = 5
# Les logs de télémétrie LiteLLM sont coupés : seules nos erreurs et nos réponses comptent.
LITELLM_LOGGERS = ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy")


def _ask_numbers(prompt, options):
    """Lit des numéros séparés par des virgules et renvoie les options correspondantes."""
    raw = input(prompt)
    picked = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit() and 1 <= int(token) <= len(options):
            picked.append(options[int(token) - 1])
    return picked


class TerminalHuman:
    """Implémentation de HumanPort dans le terminal."""

    def __init__(self, memory):
        self.memory = memory

    async def night_choice(self, state, player_id):
        legal = legal_actions(state, player_id)
        options = list(legal.targets)
        print(f"\n[Nuit] Ce que tu sais :")
        print(self.memory.context_for(player_id))
        print(f"[Nuit] Ton pouvoir ({state.player(player_id).role.name_FR}) : choisis {legal.count} cible(s).")
        for i, pid in enumerate(options, 1):
            print(f"  {i}. {state.player(pid).name}")
        picked = _ask_numbers("Numéros (ex. 1,3) : ", options)[: legal.count]
        if len(picked) != legal.count:
            print("Choix incomplet : un choix aléatoire sera fait.")
        return tuple(picked)

    async def show_night_deaths(self, state, deaths):
        names = ", ".join(state.player(pid).name for pid in deaths) or "personne"
        print(f"\n-- Morts de la nuit : {names}")

    async def day_action(self, state, player_id, seconds_left, wait, proposal, nominee_options):
        """Dans le terminal, le temps n'est pas limité pendant que tu tapes."""
        print(f"\n[Jour] Ce que tu sais (temps restant : {int(seconds_left)} s) :")
        print(self.memory.context_for(player_id))
        if proposal:
            print(f"** {state.player(proposal).name} te propose une conversation privée (choix p). **")
        print("Que fais-tu ?  m = message public | c = conversation privée | "
              + ("p = accepter la proposition | " if proposal else "")
              + ("d = désigner un joueur | " if nominee_options else "") + "f = finir ma journée")
        choice = input("> ").strip().lower()
        others = [p.id for p in state.players if p.alive and p.id != player_id]
        if choice == "m":
            text = input("Ton message public : ").strip()
            return DayAction("public", text=text) if text else None
        if choice == "p" and proposal:
            return DayAction("private", targets=(proposal,), agent_first=True)
        if choice == "c":
            for i, pid in enumerate(others, 1):
                print(f"  {i}. {state.player(pid).name}")
            picked = _ask_numbers("1 ou 2 numéros : ", others)[:2]
            return DayAction("private", targets=tuple(picked)) if picked else None
        if choice == "d" and nominee_options:
            for i, pid in enumerate(nominee_options, 1):
                print(f"  {i}. {state.player(pid).name}")
            picked = _ask_numbers("Numéro : ", nominee_options)
            return DayAction("nominate", targets=(picked[0],)) if picked else None
        if choice == "f":
            return DayAction("end")
        return None

    async def private_message(self, state, player_id):
        print("\n[Salon privé] Ce que tu sais :")
        print(self.memory.context_for(player_id))
        text = input("Ton message privé (vide = fin) : ").strip()
        return text or None

    async def show_private_replies(self, replies):
        for pid, text in replies:
            print(f"  {self.memory.name_of(pid)} : {text}")

    async def vote_on(self, state, player_id, nominee_id):
        answer = input(f"\n[Vote] {state.player(nominee_id).name} est désigné. Pour son exécution ? (o/n) : ")
        return answer.strip().lower().startswith("o")

    async def final_vote(self, state, player_id):
        options = [p.id for p in state.players if p.alive]
        print("\n[Fin du jour] Qui doit être exécuté ? (vide = personne)")
        for i, pid in enumerate(options, 1):
            print(f"  {i}. {state.player(pid).name}")
        picked = _ask_numbers("Numéro : ", options)
        return picked[0] if picked else None


def _names(state, ids):
    return ", ".join(state.player(pid).name for pid in ids) or "personne"


async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s : %(message)s")
    for name in LITELLM_LOGGERS:
        logging.getLogger(name).setLevel(logging.CRITICAL)

    rng = random.Random()
    state, agents, memory = setup_game(NAMES, HUMAN_ID, PERSONALITIES, rng)
    human = TerminalHuman(memory)

    me = state.player(HUMAN_ID)
    print(f"\nTu es {me.name}, rôle : {me.role.name_FR}")

    for _ in range(MAX_TURNS):
        print(f"\n=== Tour {state.turn} ===")
        result = await play_turn_with_human(state, rng, agents, memory, HUMAN_ID, human)
        print("-- Votes --")
        for voter, target in result.votes.items():
            cible = state.player(target).name if target else "personne"
            print(f"  {state.player(voter).name} -> {cible}")
        print(f"-- Exécuté : {_names(state, [result.executed]) if result.executed else 'personne'}")
        state = result.state
        if result.game_winner is not None:
            print(f"\n=== Fin de partie : victoire {result.game_winner.value} ===")
            return
    print("\n=== Arrêt après le nombre maximum de tours ===")


if __name__ == "__main__":
    asyncio.run(main())