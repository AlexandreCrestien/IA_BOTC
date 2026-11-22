"""Succès débloqués en fin de partie (écran de fin, inscription depuis l'écran de fin) et routes /api/me."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.accounts import service
from backend.db import GameStatus, get_session
from backend.engine.steps import Ballot
from backend.models import Alignment, GameState, Phase, Player
from backend.rules import get_role
from backend.server import game_records, game_runner as gr
from backend.server.app import app
from backend.server.session import GameSession, set_current_session

PLAYERS = {"h": "medium", "p1": "reaper", "p2": "apothecary", "p3": "watchman"}  # humain : Médium (bien)


def make_state(turn: int = 1) -> GameState:
    return GameState(turn=turn, phase=Phase.VOTE, players=tuple(
        Player(id=pid, name=pid, role=get_role(role)) for pid, role in PLAYERS.items()))


@pytest.fixture(autouse=True)
def fresh_db(db, clean_server):
    return db


@pytest.fixture
def client():
    return TestClient(app)


def account(client=None, pseudo="Vesper") -> int:
    with get_session() as db:
        user_id = service.register(db, pseudo, "mot-de-passe").id
    if client is not None:
        client.post("/api/auth/login", json={"pseudo": pseudo, "password": "mot-de-passe"})
    return user_id


def play_one_turn(monkeypatch, session, winner=Alignment.GOOD, executed="p1"):
    """Partie d'un tour : l'humain vote pour p1, qui est exécuté ; `winner` l'emporte. Renvoie le message de fin."""
    monkeypatch.setattr(gr, "setup_game", lambda names, human_id, personalities, rng: (make_state(), {}, None))

    async def one_turn(state, rng, agents, memory, human_id, port):
        return SimpleNamespace(state=make_state(1), game_winner=winner, executed=executed, night_deaths=(),
                               vote_failures=frozenset(), ballots=(Ballot("h", "p1", ghost=False),))

    monkeypatch.setattr(gr, "play_turn", one_turn)
    asyncio.run(gr.run_game(session, {"h": "h"}, []))
    requests = []
    while not session.port.requests.empty():
        requests.append(session.port.requests.get_nowait())
    return requests[-1]


def test_account_game_unlocks_and_announces_achievements(monkeypatch):
    session = GameSession(human_id="h", user_id=account())
    game_over = play_one_turn(monkeypatch, session)

    codes = [a["code"] for a in game_over["achievements"]]
    assert codes == ["win_medium", "executioner", "quick_win", "one_turn_win"]
    one_turn = game_over["achievements"][-1]
    assert one_turn["title"] == "Coup de maître"  # révélé : il vient d'être débloqué
    assert one_turn["message"] == "Talents de détective surnaturels ou chance inouïe ?"


def test_achievements_are_announced_only_the_first_time(monkeypatch):
    user_id = account()
    play_one_turn(monkeypatch, GameSession(human_id="h", user_id=user_id))
    game_over = play_one_turn(monkeypatch, GameSession(human_id="h", user_id=user_id))
    assert game_over["achievements"] == []


def test_guest_game_unlocks_nothing(monkeypatch):
    game_over = play_one_turn(monkeypatch, GameSession(human_id="h", guest_token="jeton"))
    assert game_over["achievements"] == []


def test_abandoned_game_unlocks_nothing(monkeypatch):
    monkeypatch.setattr(GameSession, "running", property(lambda self: self.outcome is None))
    user_id = account()
    session = GameSession(human_id="h", user_id=user_id, state=make_state())
    session.facts.executed_turn = 1
    set_current_session(session)
    game_records.open_record(session)
    gr.abandon_game("h")
    assert session.unlocked == []
    with get_session() as db:
        assert service.find_by_pseudo(db, "Vesper").achievements == []


def test_signup_from_end_screen_returns_the_achievements(client, monkeypatch):
    """Invité qui gagne puis s'inscrit sur l'écran de fin : partie enregistrée et succès annoncés."""
    monkeypatch.setattr(GameSession, "running", property(lambda self: self.outcome is None))
    session = GameSession(human_id="h", guest_token="jeton")
    set_current_session(session)
    play_one_turn(monkeypatch, session)
    session.state = make_state(1)  # comme après le relais de la fin de partie

    response = client.post("/api/auth/register", json={"pseudo": "Vesper", "password": "mot-de-passe",
                                                       "guest_token": "jeton"})
    body = response.json()
    assert body["game_claimed"] is True
    assert [a["code"] for a in body["achievements"]] == ["win_medium", "executioner", "quick_win", "one_turn_win"]
    games = client.get("/api/me/games").json()
    assert [(g["status"], g["turns"]) for g in games] == [("won", 1)]


# --- Routes /api/me -----------------------------------------------------------------------

def test_dashboard_routes_require_a_login(client):
    for url in ("/api/me/stats", "/api/me/games", "/api/me/achievements"):
        assert client.get(url).status_code == 401, url


def test_dashboard_after_a_game(client, monkeypatch):
    user_id = account(client)
    play_one_turn(monkeypatch, GameSession(human_id="h", user_id=user_id), winner=Alignment.EVIL)

    stats = client.get("/api/me/stats").json()
    assert (stats["played"], stats["wins"], stats["win_rate"], stats["average_turns"]) == (1, 0, 0.0, 1.0)
    assert stats["good"]["played"] == 1 and stats["evil"]["played"] == 0

    [game] = client.get("/api/me/games").json()
    assert (game["role_name"], game["alignment"], game["status"], game["turns"]) == ("Médium", "good", "lost", 1)

    achievements = {a["code"]: a for a in client.get("/api/me/achievements").json()}
    assert achievements["executioner"]["unlocked"] is True
    assert achievements["win_medium"]["unlocked"] is False
    assert achievements["one_turn_win"]["title"] == "???"


def test_interrupted_game_is_listed_but_not_counted(client, monkeypatch):
    user_id = account(client)
    session = GameSession(human_id="h", user_id=user_id, state=make_state(2))
    game_records.open_record(session)
    game_records.close_record(session, GameStatus.INTERRUPTED)

    assert client.get("/api/me/stats").json()["played"] == 0
    assert [g["status"] for g in client.get("/api/me/games").json()] == ["interrupted"]
