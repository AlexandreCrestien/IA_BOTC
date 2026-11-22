import asyncio
from types import SimpleNamespace

import pytest

from backend.engine.steps import Ballot
from backend.models import Alignment
from backend.server import game_runner as gr
from backend.server.session import GameSession, current_session


@pytest.fixture(autouse=True)
def no_game_yet(clean_server):
    """Chaque test part sans partie en cours."""


def _state(turn, dead=()):
    """État minimal : run_game lit le tour et les joueurs (voix d'outre-tombe)."""
    return SimpleNamespace(turn=turn, players=tuple(
        SimpleNamespace(id=pid, alive=pid not in dead) for pid in ("h", "p1", "p2")))


def _queued(session):
    """Messages posés par run_game dans la file du joueur, dans l'ordre (sans l'état joint)."""
    items = []
    while not session.port.requests.empty():
        request = dict(session.port.requests.get_nowait())
        request.pop("state")
        items.append(request)
    return items


def _run(monkeypatch, turns, setup_state=None):
    """Joue run_game avec un moteur factice : turns = résultats successifs de play_turn."""
    calls = []

    def fake_setup(names, human_id, personality_names, rng):
        return setup_state or _state(1), {"p1": "agent"}, "memoire"

    async def fake_turn(state, rng, agents, memory, human_id, port):
        calls.append(state.turn)
        result = turns[len(calls) - 1]
        return await result(port) if callable(result) else result  # callable : tour qui parle au port

    monkeypatch.setattr(gr, "setup_game", fake_setup)
    monkeypatch.setattr(gr, "play_turn", fake_turn)
    session = GameSession(human_id="h")
    final = asyncio.run(gr.run_game(session, {"h": "Alex"}, [], seed=1))
    return session, final, calls


def test_run_game_plays_until_victory(monkeypatch):
    states = [_state(2), _state(3)]
    session, final, calls = _run(monkeypatch, [
        SimpleNamespace(state=states[0], game_winner=None, votes={"h": "p1"}, executed="p1", vote_failures=frozenset(),
                        ballots=(Ballot("h", "p1", ghost=False),)),
        SimpleNamespace(state=states[1], game_winner=Alignment.GOOD, votes={"h": None}, executed=None, vote_failures=frozenset(), ballots=()),
    ])

    assert final is states[1]
    assert calls == [1, 2]
    assert session.memory == "memoire" and session.agents == {"p1": "agent"}  # lus par l'admin
    queued = _queued(session)
    # Le front reçoit des identifiants ; il affiche les noms lui-même
    assert queued[0] == {"kind": "vote_result", "turn": 1, "executed": "p1",
                         "votes": [{"voter": "h", "target": "p1", "ghost": False, "unavailable": False}]}
    assert queued[-1] == {"kind": "game_over", "winner": "good", "details": "Le village a rendu son dernier verdict."}


def test_evil_victory_sent_as_team(monkeypatch):
    session, _, _ = _run(monkeypatch, [
        SimpleNamespace(state=_state(1), game_winner=Alignment.EVIL, votes={}, executed=None, vote_failures=frozenset(), ballots=())])
    assert _queued(session)[-1]["winner"] == "evil"


def test_ballots_keep_the_engine_flags_and_mark_unavailable_ais(monkeypatch):
    """La mention outre-tombe vient du moteur (vote_ballots) ; le serveur ajoute seulement les IA
    qui n'ont pas répondu."""
    engine_ballots = (
        Ballot("h", "p2", ghost=False),
        Ballot("p1", "p2", ghost=True),    # morte : voix d'outre-tombe utilisée
        Ballot("p2", None, ghost=False),   # son IA n'a pas répondu : abstention
    )
    session, _, _ = _run(monkeypatch, [SimpleNamespace(
        state=_state(2), game_winner=Alignment.GOOD, votes={}, executed="p2",
        vote_failures=frozenset({"p2"}), ballots=engine_ballots)])

    ballots = {v["voter"]: v for v in _queued(session)[0]["votes"]}
    assert {pid: (v["ghost"], v["unavailable"]) for pid, v in ballots.items()} == {
        "h": (False, False), "p1": (True, False), "p2": (False, True)}


def test_game_over_comes_after_the_last_night_deaths(monkeypatch):
    """Partie gagnée pendant la nuit : les morts de la nuit (posés par le moteur) passent avant
    le résultat du tour et la fin de partie, car tout passe par la même file."""
    async def night_win(port):
        await port.show_night_deaths(_state(1), ("p1",))  # le moteur annonce le mort
        return SimpleNamespace(state=_state(1), game_winner=Alignment.EVIL, votes={}, executed=None, vote_failures=frozenset(), ballots=())

    session, _, _ = _run(monkeypatch, [night_win])
    assert [item["kind"] for item in _queued(session)] == ["night_deaths", "vote_result", "game_over"]


# --- Relance, reprise, refus et abandon (une seule partie à la fois) ----------

@pytest.fixture
def fake_game(monkeypatch):
    """run_game factice qui dure jusqu'à ce qu'on la termine ; trace les lancements et plantages.
    Le relais vers le front est remplacé par une attente."""
    events = {"started": [], "interrupted": []}
    finish = {}

    async def fake_run(session, names, personality_names, seed=None):
        events["started"].append(session.human_id)
        finish[session.human_id] = asyncio.Event()
        await finish[session.human_id].wait()
        if finish.get("crash"):
            raise RuntimeError("le moteur a planté")
        return "fini"

    async def idle_forward(session):
        await asyncio.Event().wait()

    async def fake_interrupted(player_id):
        events["interrupted"].append(player_id)

    monkeypatch.setattr(gr, "run_game", fake_run)
    monkeypatch.setattr(gr, "forward_requests", idle_forward)
    monkeypatch.setattr(gr, "send_game_interrupted", fake_interrupted)
    events["finish"] = finish
    return events


async def _tick():
    await asyncio.sleep(0.01)


def test_first_connection_starts_a_game(fake_game):
    async def scenario():
        assert gr.ensure_started("Alex") is None
        await _tick()
        session = current_session()
        assert fake_game["started"] == ["Alex"]
        assert session.human_id == "Alex" and session.running
        assert not session.forward_task.done()  # le relais vers le front tourne
        session.stop()
    asyncio.run(scenario())


def test_same_pseudo_resumes_the_current_game(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        session = current_session()
        assert gr.ensure_started("Alex") is None
        await _tick()
        assert fake_game["started"] == ["Alex"]  # pas de seconde partie
        assert current_session() is session
        session.stop()
    asyncio.run(scenario())


def test_other_pseudo_refused_during_a_game(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        assert gr.ensure_started("Bea") == gr.REFUSED_BUSY
        current_session().stop()
    asyncio.run(scenario())


@pytest.mark.parametrize("pseudo", ["", "  ", "marIA", "MARIA", "p1", "game_master", "codex",
                                    "Jean?x", "Ana#1", "Jean/Paul", "Jean Paul", "<b>x</b>", "a" * 21])
def test_invalid_pseudo_refused(fake_game, pseudo):
    assert gr.ensure_started(pseudo) == gr.REFUSED_PSEUDO
    assert fake_game["started"] == []


def test_new_game_after_the_previous_one_ended(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        previous = current_session()
        fake_game["finish"]["Alex"].set()  # la partie se termine
        await _tick()
        assert gr.ensure_started("Bea") is None  # n'importe quel pseudo peut rejouer
        await _tick()
        assert fake_game["started"] == ["Alex", "Bea"]
        assert previous.forward_task.cancelled()  # le relais de l'ancienne partie est arrêté
        assert current_session().human_id == "Bea"  # nouvelle session : rien de l'ancienne partie
        current_session().stop()
    asyncio.run(scenario())


def test_abandon_stops_the_game_and_allows_a_new_one(fake_game):
    async def scenario():
        gr.ensure_started("Alex")
        await _tick()
        session = current_session()
        assert gr.abandon_game("Alex") is True
        await _tick()
        assert session.game_task.cancelled() and session.forward_task.cancelled()
        assert current_session() is None
        assert fake_game["interrupted"] == []  # un abandon n'est pas un plantage
        assert gr.ensure_started("Alex") is None
        await _tick()
        assert fake_game["started"] == ["Alex", "Alex"]
        current_session().stop()
    asyncio.run(scenario())


def test_abandon_refused_without_game_or_for_another_player(fake_game):
    async def scenario():
        assert gr.abandon_game("Alex") is False
        gr.ensure_started("Alex")
        await _tick()
        assert gr.abandon_game("Bea") is False
        assert current_session().running
        current_session().stop()
    asyncio.run(scenario())


def test_crash_warns_the_player_and_allows_a_new_game(fake_game):
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
        current_session().stop()
    asyncio.run(scenario())


@pytest.mark.parametrize("pseudo", ["Zoé", "Jean-Paul", "O'Neil", "O’Neil", "mad_max42", "a" * 20])
def test_valid_pseudo_accepted(pseudo):
    assert gr.can_join(pseudo) is None
