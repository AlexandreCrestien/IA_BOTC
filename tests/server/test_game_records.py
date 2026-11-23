"""Partie liée au compte : enregistrement (en cours, victoire, défaite, abandon, interrompue),
rattachement d'une partie d'invité, règles d'accès selon le compte, routes /api/game."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.accounts import service
from backend.db import GameRecord, GameStatus, get_session
from backend.models import Alignment, GameState, Phase, Player
from backend.rules import get_role
from backend.server import game_records, game_runner as gr
from backend.server.app import app
from backend.server.session import GameSession, current_session, set_current_session

PLAYERS = {"h": "medium", "p1": "reaper", "p2": "apothecary", "p3": "watchman"}  # humain : Médium (bien)


def make_state(turn: int = 1, human: str = "h") -> GameState:
    """Partie de 4 joueurs ; l'humain (identifiant `human`) est le Médium."""
    ids = {"h": human}
    return GameState(turn=turn, phase=Phase.NIGHT, players=tuple(
        Player(id=ids.get(pid, pid), name=ids.get(pid, pid), role=get_role(role)) for pid, role in PLAYERS.items()))


@pytest.fixture(autouse=True)
def fresh_db(db, clean_server):
    """Base vide et aucune partie au début de chaque test."""
    return db


def account(pseudo="Vesper") -> int:
    with get_session() as db:
        return service.register(db, pseudo, "mot-de-passe", f"{pseudo.lower()}@exemple.fr").id


def records() -> list[GameRecord]:
    with get_session() as db:
        return list(db.scalars(select(GameRecord).order_by(GameRecord.id)))


def running_session(monkeypatch, user_id=None, guest_token=None, state=None, human_id="h") -> GameSession:
    """Session courante d'une partie qui tourne (sans moteur)."""
    monkeypatch.setattr(GameSession, "running", property(lambda self: self.outcome is None))
    if state is not None:
        state = make_state(state.turn, human_id)
    session = GameSession(human_id=human_id, user_id=user_id, guest_token=guest_token, state=state)
    set_current_session(session)
    return session


def play(monkeypatch, session, winner, final_turn=3):
    """Joue run_game avec un moteur factice : un seul tour, qui donne la victoire à `winner`."""
    monkeypatch.setattr(gr, "setup_game", lambda names, human_id, personalities, rng: (make_state(), {}, None))

    async def one_turn(state, rng, agents, memory, human_id, port):
        assert records()[-1].status == GameStatus.IN_PROGRESS if session.user_id else not records()
        return SimpleNamespace(state=make_state(final_turn), game_winner=winner, executed=None,
                               night_deaths=(), vote_failures=frozenset(), ballots=())

    monkeypatch.setattr(gr, "play_turn", one_turn)
    asyncio.run(gr.run_game(session, {"h": "h"}, []))


# --- Enregistrement ---------------------------------------------------------------------

def test_logged_in_game_is_recorded_then_won(monkeypatch):
    user_id = account()
    session = GameSession(human_id="h", user_id=user_id)
    play(monkeypatch, session, Alignment.GOOD)

    [record] = records()
    assert (record.user_id, record.role, record.alignment) == (user_id, "medium", Alignment.GOOD)
    assert (record.status, record.turns) == (GameStatus.WON, 3)
    assert record.ended_at is not None


def test_logged_in_game_lost(monkeypatch):
    session = GameSession(human_id="h", user_id=account())
    play(monkeypatch, session, Alignment.EVIL)
    assert records()[0].status == GameStatus.LOST


def test_guest_game_is_not_recorded(monkeypatch):
    session = GameSession(human_id="h", guest_token="jeton")
    play(monkeypatch, session, Alignment.GOOD)
    assert records() == []
    assert session.outcome == GameStatus.WON  # gardée en mémoire : l'invité peut encore s'inscrire


def test_abandon_is_a_defeat(monkeypatch):
    session = running_session(monkeypatch, user_id=account(), state=make_state(turn=4))
    game_records.open_record(session)
    assert gr.abandon_game("h") is True

    [record] = records()
    assert (record.status, record.turns) == (GameStatus.ABANDONED, 4)
    assert current_session() is None


def test_crash_is_interrupted_and_not_counted():
    async def scenario():
        session = GameSession(human_id="h", user_id=account(), state=make_state(turn=2))
        game_records.open_record(session)

        async def crash():
            raise RuntimeError("le moteur a planté")

        task = asyncio.ensure_future(crash())
        await asyncio.gather(task, return_exceptions=True)
        gr._on_game_end(session, task)
        await asyncio.sleep(0)  # laisse partir l'avertissement au joueur

    asyncio.run(scenario())
    assert records()[0].status == GameStatus.INTERRUPTED


def test_guests_receive_a_token_and_accounts_do_not():
    async def scenario():
        guest = gr.start_game("h", {"h": "h"}, [], user_id=None)
        player = gr.start_game("Vesper", {"Vesper": "Vesper"}, [], user_id=7)
        for session in (guest, player):
            session.stop()
        return guest, player

    guest, player = asyncio.run(scenario())
    assert guest.guest_token and guest.user_id is None
    assert player.guest_token is None and player.user_id == 7


# --- Rattachement d'une partie d'invité --------------------------------------------------

def test_guest_claims_running_game(monkeypatch):
    session = running_session(monkeypatch, guest_token="jeton", state=make_state(turn=2))
    user_id = account()
    assert game_records.claim_guest_game(user_id, "jeton") is True
    assert session.user_id == user_id and session.guest_token is None
    [record] = records()
    assert (record.user_id, record.status, record.turns) == (user_id, GameStatus.IN_PROGRESS, 2)
    assert game_records.claim_guest_game(account("Ombre"), "jeton") is False  # usage unique


def test_wrong_or_missing_token_does_not_claim(monkeypatch):
    running_session(monkeypatch, guest_token="jeton", state=make_state())
    user_id = account()
    assert game_records.claim_guest_game(user_id, "autre") is False
    assert game_records.claim_guest_game(user_id, None) is False
    assert records() == []


def test_finished_game_claimed_from_end_screen(monkeypatch):
    session = running_session(monkeypatch, guest_token="jeton", state=make_state(turn=3))
    game_records.close_record(session, GameStatus.LOST)
    assert game_records.claim_guest_game(account(), "jeton") is True
    [record] = records()
    assert (record.status, record.turns) == (GameStatus.LOST, 3)
    assert record.ended_at is not None


def test_interrupted_game_cannot_be_claimed(monkeypatch):
    session = running_session(monkeypatch, guest_token="jeton", state=make_state())
    game_records.close_record(session, GameStatus.INTERRUPTED)
    assert game_records.claim_guest_game(account(), "jeton") is False
    assert records() == []


def test_claim_before_setup_is_recorded_once_the_game_is_set_up(monkeypatch):
    """Inscription pendant la mise en place (quelques secondes) : la partie est enregistrée juste après."""
    session = GameSession(human_id="h", guest_token="jeton")
    set_current_session(session)
    monkeypatch.setattr(GameSession, "running", property(lambda self: True))
    user_id = account()
    assert game_records.claim_guest_game(user_id, "jeton") is True
    assert records() == []
    play(monkeypatch, session, Alignment.GOOD)
    assert [(r.user_id, r.status) for r in records()] == [(user_id, GameStatus.WON)]


# --- Qui peut rejoindre quelle partie ---------------------------------------------------

def user(pseudo="Vesper"):
    with get_session() as db:
        return service.find_by_pseudo(db, pseudo)


def test_guest_cannot_take_an_account_pseudo():
    account("Vesper")
    assert gr.can_join("vesper") == gr.REFUSED_ACCOUNT_PSEUDO
    assert gr.can_join("Ombre") is None


def test_account_plays_under_its_own_pseudo():
    account("Vesper")
    assert gr.can_join("VESPER", user()) is None
    assert gr.can_join("Ombre", user()) == gr.REFUSED_OTHER_ACCOUNT


def test_account_game_can_only_be_resumed_by_its_owner(monkeypatch):
    account("Vesper")
    account("Ombre")
    running_session(monkeypatch, user_id=user("Vesper").id, human_id="Vesper")
    assert gr.can_join("Vesper", user("Vesper")) is None
    assert gr.can_join("Vesper") == gr.REFUSED_OWNER
    assert gr.can_join("Vesper", user("Ombre")) == gr.REFUSED_OWNER
    assert gr.can_join("Ombre", user("Ombre")) == gr.REFUSED_BUSY


def test_guest_game_resumed_with_the_same_pseudo(monkeypatch):
    running_session(monkeypatch, guest_token="jeton", human_id="Lune")
    assert gr.can_join("Lune") is None
    assert gr.can_join("Soleil") == gr.REFUSED_BUSY


# --- Routes /api/game, profil et inscription ----------------------------------------------

@pytest.fixture
def client():
    return TestClient(app)


def log_in(client, pseudo="Vesper"):
    assert client.post("/api/auth/login", json={"login": pseudo, "password": "mot-de-passe"}).status_code == 200


def test_current_game_without_game(client):
    assert client.get("/api/game/current").json() == {"running": False, "pseudo": None, "turn": None, "yours": False}


def test_current_account_game(client, monkeypatch):
    account("Vesper")
    account("Ombre")
    running_session(monkeypatch, user_id=user("Vesper").id, human_id="Vesper", state=make_state(turn=2))

    assert client.get("/api/game/current").json()["yours"] is False  # invité
    log_in(client, "Ombre")
    assert client.get("/api/game/current").json()["yours"] is False
    log_in(client, "Vesper")
    assert client.get("/api/game/current").json() == {"running": True, "pseudo": "Vesper", "turn": 2, "yours": True}


def test_current_guest_game(client, monkeypatch):
    running_session(monkeypatch, guest_token="jeton", human_id="Lune")
    assert client.get("/api/game/current").json()["yours"] is True


def test_abandon_from_dashboard(client, monkeypatch):
    account("Vesper")
    account("Ombre")
    session = running_session(monkeypatch, user_id=user("Vesper").id, human_id="Vesper", state=make_state(turn=3))
    game_records.open_record(session)

    assert client.post("/api/game/abandon").status_code == 401
    log_in(client, "Ombre")
    assert client.post("/api/game/abandon").status_code == 404
    log_in(client, "Vesper")
    assert client.post("/api/game/abandon").status_code == 204
    assert records()[0].status == GameStatus.ABANDONED
    assert current_session() is None
    assert client.post("/api/game/abandon").status_code == 404


def test_pseudo_cannot_change_during_own_game(client, monkeypatch):
    account("Vesper")
    log_in(client)
    session = running_session(monkeypatch, user_id=user("Vesper").id, human_id="Vesper")
    change = {"current_password": "mot-de-passe", "pseudo": "Ombre"}

    response = client.patch("/api/account/pseudo", json=change)
    assert (response.status_code, response.json()["detail"]) == (409, "Impossible de changer de pseudo pendant une partie en cours.")
    session.outcome = GameStatus.WON  # partie terminée
    assert client.patch("/api/account/pseudo", json=change).status_code == 200


def test_register_with_guest_token_claims_the_game(client, monkeypatch):
    running_session(monkeypatch, guest_token="jeton", human_id="Lune", state=make_state())
    response = client.post("/api/auth/register", json={"pseudo": "Vesper", "email": "vesper@exemple.fr",
                                                       "password": "mot-de-passe",
                                                       "guest_token": "jeton"})
    assert response.status_code == 201 and response.json()["game_claimed"] is True
    assert records()[0].user_id == response.json()["id"]


def test_login_with_guest_token_claims_the_game(client, monkeypatch):
    account("Vesper")
    running_session(monkeypatch, guest_token="jeton", human_id="Lune", state=make_state())
    response = client.post("/api/auth/login", json={"login": "Vesper", "password": "mot-de-passe", "guest_token": "jeton"})
    assert response.json()["game_claimed"] is True


def test_login_without_token_claims_nothing(client, monkeypatch):
    account("Vesper")
    running_session(monkeypatch, guest_token="jeton", human_id="Lune", state=make_state())
    assert client.post("/api/auth/login", json={"login": "Vesper", "password": "mot-de-passe"}).json()["game_claimed"] is False
    assert records() == []


# --- WebSocket : identité par le cookie ----------------------------------------------------

@pytest.fixture
def started(monkeypatch):
    """ensure_started réel, mais sans lancer de partie : on note qui la lance, et pour quel compte."""
    calls = []

    def fake_start(human_id, names, personality_names, seed=None, user_id=None):
        session = GameSession(human_id=human_id, user_id=user_id,
                              guest_token=None if user_id else "jeton-invite")
        set_current_session(session)
        calls.append((human_id, user_id))
        return session

    monkeypatch.setattr(gr, "start_game", fake_start)
    return calls


def first_messages(conn, count):
    return [json.loads(conn.receive_text()) for _ in range(count)]


def test_websocket_uses_the_account_cookie(client, started):
    account("Vesper")
    log_in(client)
    with client.websocket_connect("/ws/Vesper") as conn:
        assert first_messages(conn, 1)[0]["type"] == "connected"
    assert started == [("Vesper", user("Vesper").id)]


def test_websocket_guest_receives_its_token(client, started):
    with client.websocket_connect("/ws/Lune") as conn:
        messages = first_messages(conn, 2)
    assert messages[1] == {"type": "guest_session", "guest_token": "jeton-invite"}
    assert started == [("Lune", None)]


def test_websocket_refuses_a_guest_with_an_account_pseudo(client, started):
    account("Vesper")
    with client.websocket_connect("/ws/Vesper") as conn:
        with pytest.raises(Exception) as closed:
            conn.receive_text()
    assert getattr(closed.value, "reason", None) == gr.REFUSED_ACCOUNT_PSEUDO
    assert started == []
