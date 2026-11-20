import asyncio
from types import SimpleNamespace

import pytest

from backend.server import game_runner as gr


@pytest.fixture(autouse=True)
def no_game_yet(monkeypatch):
    """Chaque test part sans partie en cours (l'état du module est global)."""
    monkeypatch.setattr(gr, "_current", None)
    monkeypatch.setattr(gr, "_current_human", None)


def _state(turn):
    """État minimal : run_game lit le tour et les joueurs (pour envoyer des noms au front)."""
    return SimpleNamespace(turn=turn, players=(
        SimpleNamespace(id="h", name="Alex"), SimpleNamespace(id="p1", name="marIA"),
    ))


def _queued(port):
    """Messages posés par run_game dans la file du joueur, dans l'ordre."""
    items = []
    while not port.requests.empty():
        items.append(port.requests.get_nowait())
    return items


def test_run_game_joue_jusqu_a_la_victoire(monkeypatch):
    calls = []
    registered = []
    states = [_state(1), _state(2), _state(3)]

    def fake_setup(names, human_id, personality_names, rng):
        return states[0], {}, "memoire"

    async def fake_turn(state, rng, agents, memory, human_id, port):
        calls.append(state.turn)
        if state is states[0]:
            return SimpleNamespace(state=states[1], game_winner=None, votes={"h": "p1"}, executed="p1")
        return SimpleNamespace(state=states[2], game_winner="bons", votes={"h": None}, executed=None)

    monkeypatch.setattr(gr, "setup_game", fake_setup)
    monkeypatch.setattr(gr, "play_turn_with_human", fake_turn)
    monkeypatch.setattr(gr, "register_human", lambda pid, port: registered.append((pid, port)))

    final = asyncio.run(gr.run_game({"h": "Alex"}, "h", [], seed=1))

    assert final is states[2]
    assert calls == [1, 2]
    assert registered[0][0] == "h"
    queued = _queued(registered[0][1])
    # Le front reçoit des noms, jamais les identifiants internes
    assert queued[0] == {"kind": "vote_result", "turn": 1, "executed": "marIA",
                         "votes": [{"voter": "Alex", "target": "marIA"}]}
    assert queued[-1]["kind"] == "game_over" and queued[-1]["winner"] == "bons"


def test_fin_de_partie_apres_les_morts_de_la_derniere_nuit(monkeypatch):
    """Partie gagnée pendant la nuit : les morts de la nuit (posés par le moteur) passent avant
    le résultat du tour et la fin de partie, car tout passe par la même file."""
    registered = []

    def fake_setup(names, human_id, personality_names, rng):
        return _state(1), {}, "memoire"

    async def fake_turn(state, rng, agents, memory, human_id, port):
        await port.requests.put({"kind": "night_deaths", "deaths": ["p1"]})  # le moteur annonce le mort
        return SimpleNamespace(state=_state(1), game_winner="mal", votes={}, executed=None)

    monkeypatch.setattr(gr, "setup_game", fake_setup)
    monkeypatch.setattr(gr, "play_turn_with_human", fake_turn)
    monkeypatch.setattr(gr, "register_human", lambda pid, port: registered.append((pid, port)))

    asyncio.run(gr.run_game({"h": "Alex"}, "h", [], seed=1))

    assert [item["kind"] for item in _queued(registered[0][1])] == ["night_deaths", "vote_result", "game_over"]


def test_start_game_ne_lance_pas_deux_parties(monkeypatch):
    async def fake_run(*args, **kwargs):
        await asyncio.sleep(0.05)
        return "fini"

    monkeypatch.setattr(gr, "run_game", fake_run)

    async def scenario():
        first = gr.start_game({"h": "Alex"}, "h", [])
        second = gr.start_game({"h": "Alex"}, "h", [])
        assert first is second
        await first

    asyncio.run(scenario())


# --- Relance, reprise, refus et abandon (une seule partie à la fois) ----------

@pytest.fixture
def fake_game(monkeypatch):
    """run_game factice qui dure jusqu'à ce qu'on la termine ; trace les lancements et nettoyages."""
    events = {"started": [], "reset": [], "interrupted": []}
    finish = {}

    async def fake_run(names, human_id, personality_names, seed=None):
        events["started"].append(human_id)
        finish[human_id] = asyncio.Event()
        await finish[human_id].wait()
        if finish.get("crash"):
            raise RuntimeError("le moteur a planté")
        return "fini"

    async def fake_interrupted(player_id):
        events["interrupted"].append(player_id)

    monkeypatch.setattr(gr, "run_game", fake_run)
    monkeypatch.setattr(gr, "reset_player", lambda pid: events["reset"].append(pid))
    monkeypatch.setattr(gr, "send_game_interrupted", fake_interrupted)
    events["finish"] = finish
    return events


async def _tick():
    await asyncio.sleep(0.01)


def test_premiere_connexion_lance_une_partie(fake_game):
    async def scenario():
        assert gr.ensure_started("Alex") is None
        await _tick()
        assert fake_game["started"] == ["Alex"]
        gr._current.cancel()
    asyncio.run(scenario())


def test_meme_pseudo_reprend_la_partie_en_cours(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        assert gr.ensure_started("Alex") is None
        await _tick()
        assert fake_game["started"] == ["Alex"]  # pas de seconde partie
        gr._current.cancel()
    asyncio.run(scenario())


def test_autre_pseudo_refuse_pendant_une_partie(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        assert gr.ensure_started("Bea") == gr.REFUSED_BUSY
        gr._current.cancel()
    asyncio.run(scenario())


@pytest.mark.parametrize("pseudo", ["", "  ", "marIA", "MARIA", "p1", "game_master"])
def test_pseudo_invalide_refuse(fake_game, pseudo):
    assert gr.ensure_started(pseudo) == gr.REFUSED_PSEUDO
    assert fake_game["started"] == []


def test_nouvelle_partie_apres_la_fin_de_la_precedente(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        fake_game["finish"]["Alex"].set()  # la partie se termine
        await _tick()
        assert gr.ensure_started("Bea") is None  # n'importe quel pseudo peut rejouer
        await _tick()
        assert fake_game["started"] == ["Alex", "Bea"]
        assert "Alex" in fake_game["reset"]  # traces de l'ancienne partie effacées
        gr._current.cancel()
    asyncio.run(scenario())


def test_abandon_arrete_la_partie_et_permet_d_en_relancer_une(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        task = gr._current
        assert gr.abandon_game("Alex") is True
        await _tick()
        assert task.cancelled()
        assert fake_game["reset"] == ["Alex"]
        assert fake_game["interrupted"] == []  # un abandon n'est pas un plantage
        assert gr.ensure_started("Alex") is None
        await _tick()
        assert fake_game["started"] == ["Alex", "Alex"]
        gr._current.cancel()
    asyncio.run(scenario())


def test_abandon_refuse_sans_partie_ou_pour_un_autre_joueur(fake_game):
    async def scenario():
        assert gr.abandon_game("Alex") is False
        gr.ensure_started("Alex")
        await _tick()
        assert gr.abandon_game("Bea") is False
        assert not gr._current.done()
        gr._current.cancel()
    asyncio.run(scenario())


def test_plantage_previent_le_joueur_et_permet_de_relancer(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        fake_game["finish"]["crash"] = True
        fake_game["finish"]["Alex"].set()
        await _tick()
        assert fake_game["interrupted"] == ["Alex"]
        assert gr.ensure_started("Alex") is None  # une nouvelle partie démarre
        await _tick()
        assert fake_game["started"] == ["Alex", "Alex"]
        gr._current.cancel()
    asyncio.run(scenario())
