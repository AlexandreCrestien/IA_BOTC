"""Historique détaillé des parties (panel admin) et registre des modifications des comptes :
enregistrement, consultation par l'admin, suppression avec le compte, durées de conservation, export."""
import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.accounts import service
from backend.db import AccountEvent, GameDetail, GameRecord, GameStatus, User, get_session
from backend.db.models import utcnow
from backend.engine.setup import setup_game
from backend.server import game_records
from backend.server import game_runner as gr
from backend.server.app import app
from backend.server.session import GameSession, set_current_session

NAMES = {"h": "Vesper", "p1": "marIA", "p2": "tobIAs", "p3": "mAIsie", "p4": "adrIAn", "p5": "dIAne"}
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


@pytest.fixture
def client(clean_server, monkeypatch):
    monkeypatch.setenv("ADMIN_PSEUDO", "Gardien")
    monkeypatch.setenv("ADMIN_PASSWORD", "mot-de-passe-admin")
    monkeypatch.setenv("ADMIN_EMAIL", "gardien@exemple.fr")
    with TestClient(app) as client:
        yield client


def account(pseudo="Vesper") -> int:
    with get_session() as db:
        user = service.register(db, pseudo, "mot-de-passe", f"{pseudo.lower()}@exemple.fr")
        user.email_verified_at = utcnow()
        db.commit()
        return user.id


def finished_game(user_id, status=GameStatus.WON) -> GameSession:
    """Partie réelle (moteur, mémoire) d'un compte, enregistrée puis terminée avec `status`."""
    state, agents, memory = setup_game(NAMES, "h", PERSONALITIES, random.Random(0))
    session = GameSession(human_id="h", user_id=user_id, state=state, memory=memory, agents=agents)
    game_records.open_record(session)
    game_records.close_record(session, status, turns=3)
    return session


def admin_client(client):
    client.post("/api/auth/login", json={"login": "Gardien", "password": "mot-de-passe-admin"})
    return client


# --- Enregistrement du détail ---------------------------------------------------------------

def test_detail_is_saved_when_an_account_game_ends(db):
    user_id = account()
    finished_game(user_id)
    detail = db.query(GameDetail).one()
    assert detail.game_id == db.query(GameRecord).one().id
    assert detail.data["human"] == "Vesper" and len(detail.data["players"]) == 6
    assert set(detail.data["agent_histories"]) == {"marIA", "tobIAs", "mAIsie", "adrIAn", "dIAne"}
    assert (detail.data["status"], detail.data["turn"], detail.data["game_in_progress"]) == ("victoire", 3, False)


@pytest.mark.parametrize("status, label", [(GameStatus.ABANDONED, "abandonnée"), (GameStatus.INTERRUPTED, "interrompue")])
def test_abandoned_and_interrupted_games_keep_their_detail(db, status, label):
    finished_game(account(), status)
    assert db.query(GameDetail).one().data["status"] == label


def test_guest_game_has_no_detail(db):
    state, agents, memory = setup_game(NAMES, "h", PERSONALITIES, random.Random(0))
    session = GameSession(human_id="h", guest_token="jeton", state=state, memory=memory, agents=agents)
    game_records.close_record(session, GameStatus.WON)
    assert db.query(GameDetail).count() == 0


def test_game_in_progress_has_no_detail_yet(db):
    state, agents, memory = setup_game(NAMES, "h", PERSONALITIES, random.Random(0))
    session = GameSession(human_id="h", user_id=account(), state=state, memory=memory, agents=agents)
    game_records.open_record(session)
    assert db.query(GameRecord).count() == 1 and db.query(GameDetail).count() == 0


# --- Registre des modifications ---------------------------------------------------------------

def kinds(db, user_id):
    return [e.kind for e in db.query(AccountEvent).filter_by(user_id=user_id).order_by(AccountEvent.id)]


def test_account_changes_are_logged_without_values(db):
    user = service.register(db, "Vesper", "mot-de-passe", "vesper@exemple.fr")
    service.verify_email(db, service.create_verification_token(db, user))
    service.change_pseudo(db, user, "mot-de-passe", "Ombre")
    service.change_password(db, user, "mot-de-passe", "nouveau-mdp")
    token = service.change_email(db, user, "nouveau-mdp", "nouveau@exemple.fr")
    service.verify_email(db, token)
    service.reset_password_with_token(db, service.create_reset_token(db, user), "encore-un-mdp")
    service.reset_password(db, user)
    assert kinds(db, user.id) == ["account_created", "email_verified", "pseudo_changed", "password_changed",
                                  "email_change_requested", "email_changed", "password_reset_link",
                                  "password_reset_admin"]
    assert set(AccountEvent.__table__.columns.keys()) == {"id", "user_id", "kind", "created_at"}  # jamais de valeur


def test_typo_correction_is_logged(db):
    user = service.register(db, "Vesper", "mot-de-passe", "vespre@exemple.fr")
    service.change_email(db, user, "mot-de-passe", "vesper@exemple.fr")
    assert kinds(db, user.id)[-1] == "email_corrected"


# --- Suppression et durées de conservation --------------------------------------------------------

def test_deleting_an_account_removes_details_and_log_but_keeps_the_anonymous_summary(db):
    user_id, other_id = account(), account("Ombre")
    finished_game(user_id)
    finished_game(other_id)
    user = db.get(User, user_id)
    service.delete_account(db, user)

    assert {d.game_id for d in db.query(GameDetail)} == {db.query(GameRecord).filter_by(user_id=other_id).one().id}
    assert db.query(AccountEvent).filter_by(user_id=user_id).count() == 0
    anonymous = db.query(GameRecord).filter(GameRecord.user_id.is_(None)).one()
    assert anonymous.status == GameStatus.WON


def test_retention_periods(db):
    user_id = account()
    finished_game(user_id)
    finished_game(user_id)
    old_detail, recent_detail = db.query(GameDetail).order_by(GameDetail.id).all()
    old_detail.created_at = utcnow() - timedelta(days=184)  # plus de 6 mois
    recent_detail.created_at = utcnow() - timedelta(days=150)
    old_event = db.query(AccountEvent).one()  # « compte créé »
    old_event.created_at = utcnow() - timedelta(days=366)
    db.add(AccountEvent(user_id=user_id, kind="pseudo_changed", created_at=utcnow() - timedelta(days=300)))
    db.commit()

    assert service.delete_expired_records(db) == 2
    assert [d.id for d in db.query(GameDetail)] == [recent_detail.id]
    assert [e.kind for e in db.query(AccountEvent)] == ["pseudo_changed"]
    assert db.query(GameRecord).count() == 2  # le résumé des parties, lui, reste


def test_daily_cleanup_applies_the_retention_periods(client):
    from backend.server.account_removal import purge_inactive_accounts
    user_id = account()
    finished_game(user_id)
    with get_session() as db:
        db.query(GameDetail).one().created_at = utcnow() - timedelta(days=200)
        db.commit()
    purge_inactive_accounts()
    with get_session() as db:
        assert db.query(GameDetail).count() == 0


# --- Panel admin -------------------------------------------------------------------------------------

def test_admin_lists_a_players_games(client):
    user_id = account()
    finished_game(user_id, GameStatus.LOST)
    games = admin_client(client).get(f"/admin/users/{user_id}/games").json()
    assert [(g["role_name"] != "", g["status"], g["turns"], g["has_detail"]) for g in games] == [(True, "lost", 3, True)]


def test_admin_opens_a_game_detail(client):
    user_id = account()
    finished_game(user_id)
    game_id = admin_client(client).get(f"/admin/users/{user_id}/games").json()[0]["id"]
    body = client.get(f"/admin/games/{game_id}").json()
    assert body["game"]["pseudo"] == "Vesper" and body["game"]["status"] == "won"
    assert body["detail"]["human"] == "Vesper" and body["detail"]["agent_histories"]


def test_purged_or_unknown_detail_is_a_404(client):
    user_id = account()
    finished_game(user_id)
    with get_session() as db:
        game_id = db.query(GameRecord).one().id
        db.query(GameDetail).delete()
        db.commit()
    admin_client(client)
    assert client.get(f"/admin/users/{user_id}/games").json()[0]["has_detail"] is False
    response = client.get(f"/admin/games/{game_id}")
    assert response.status_code == 404 and "6 mois" in response.json()["detail"]
    assert client.get("/admin/games/999").status_code == 404
    assert client.get("/admin/users/999/games").status_code == 404


def test_admin_sees_the_account_log(client):
    user_id = account()
    with get_session() as db:
        service.change_pseudo(db, db.get(User, user_id), "mot-de-passe", "Ombre")
    events = admin_client(client).get(f"/admin/users/{user_id}/events").json()
    assert [e["label"] for e in events] == ["Pseudo modifié", "Compte créé"]  # du plus récent au plus ancien
    assert all(e["date"].endswith("+00:00") for e in events)


def test_history_routes_are_admin_only(client):
    user_id = account()
    player = TestClient(app)
    player.post("/api/auth/login", json={"login": "Vesper", "password": "mot-de-passe"})
    for url in (f"/admin/users/{user_id}/games", f"/admin/users/{user_id}/events", "/admin/games/1"):
        assert TestClient(app).get(url).status_code == 401
        assert player.get(url).status_code == 403


# --- Droit d'accès : l'export contient tout ----------------------------------------------------------

def test_export_contains_the_game_detail_and_the_account_log(client):
    user_id = account()
    finished_game(user_id)
    client.post("/api/auth/login", json={"login": "Vesper", "password": "mot-de-passe"})
    data = client.get("/api/me/export").json()
    assert data["games"][0]["detail"]["human"] == "Vesper"
    assert [e["event"] for e in data["account_history"]] == ["Compte créé"]


def test_full_game_saves_its_detail(client, monkeypatch):
    """Partie jouée par run_game jusqu'à la victoire : le détail est enregistré à la fin."""
    import asyncio
    from types import SimpleNamespace
    user_id = account()
    state, agents, memory = setup_game(NAMES, "h", PERSONALITIES, random.Random(0))
    monkeypatch.setattr(gr, "setup_game", lambda names, human_id, personalities, rng: (state, agents, memory))

    async def one_turn(state, rng, agents, memory, human_id, port):
        return SimpleNamespace(state=state, game_winner=state.player("h").role.alignment, executed=None,
                               night_deaths=(), vote_failures=frozenset(), ballots=())

    monkeypatch.setattr(gr, "play_turn", one_turn)
    session = GameSession(human_id="h", user_id=user_id)
    set_current_session(session)
    asyncio.run(gr.run_game(session, NAMES, PERSONALITIES))
    with get_session() as db:
        assert db.query(GameDetail).one().data["status"] == "victoire"
