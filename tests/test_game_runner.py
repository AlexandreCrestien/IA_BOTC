import asyncio
from types import SimpleNamespace

from backend.server import game_runner as gr


def test_run_game_joue_jusqu_a_la_victoire(monkeypatch):
    calls = []
    registered = []

    def fake_setup(names, human_id, personality_names, rng):
        return "etat0", {}, "memoire"

    async def fake_turn(state, rng, agents, memory, human_id, port):
        calls.append(state)
        if state == "etat0":
            return SimpleNamespace(state="etat1", game_winner=None)
        return SimpleNamespace(state="etat2", game_winner="bons")

    monkeypatch.setattr(gr, "setup_game", fake_setup)
    monkeypatch.setattr(gr, "play_turn_with_human", fake_turn)
    monkeypatch.setattr(gr, "register_human", lambda pid, port: registered.append((pid, port)))

    final = asyncio.run(gr.run_game({"h": "Alex"}, "h", [], seed=1))

    assert final == "etat2"
    assert calls == ["etat0", "etat1"]
    assert registered[0][0] == "h"


def test_start_game_ne_lance_pas_deux_parties(monkeypatch):
    async def fake_run(*args, **kwargs):
        await asyncio.sleep(0.05)
        return "fini"

    monkeypatch.setattr(gr, "run_game", fake_run)
    monkeypatch.setattr(gr, "_current", None)

    async def scenario():
        first = gr.start_game({"h": "Alex"}, "h", [])
        second = gr.start_game({"h": "Alex"}, "h", [])
        assert first is second
        await first

    asyncio.run(scenario())