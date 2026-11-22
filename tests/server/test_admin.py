"""Routes d'administration : réservées au compte admin ; état complet de la partie en cours (rien n'est caché)."""
import random

import pytest
from fastapi.testclient import TestClient

from backend.engine.setup import setup_game
from backend.engine.steps import record_night_choices
from backend.models import EventType
from backend.server import admin
from backend.server.app import app
from backend.server.schemas import NightHistoryEntry, VoteHistoryEntry
from backend.server.session import GameSession, set_current_session
from backend.accounts.service import ensure_admin, register
from backend.accounts.tokens import COOKIE_NAME
from backend.db import get_session

NAMES = {"h": "Alex", "p1": "marIA", "p2": "tobIAs", "p3": "mAIsie", "p4": "adrIAn", "p5": "dIAne"}
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


@pytest.fixture
def session(clean_server, monkeypatch):
    """Partie mise en place par le vrai moteur (sans appel LLM), dans la session courante comme par game_runner."""
    state, agents, memory = setup_game(NAMES, "h", PERSONALITIES, random.Random(0))
    session = GameSession(human_id="h", state=state, memory=memory, agents=agents)
    monkeypatch.setattr(GameSession, "running", property(lambda self: True))
    set_current_session(session)
    return session


@pytest.fixture
def game(session):
    return session.state, session.memory


def test_without_game(clean_server):
    view = admin.build_debug_state()
    assert view["game_in_progress"] is False
    assert view["message"] == "Aucune partie n'a encore été lancée."


def test_players_with_role_team_and_personality(game):
    state, _ = game
    view = admin.build_debug_state()

    assert view["status"] == "en cours"
    assert view["human"] == "Alex"
    assert len(view["players"]) == 6
    by_name = {p["name"]: p for p in view["players"]}
    for player in state.players:
        assert by_name[player.name]["role"] == player.role.name_FR  # rôles réels, rien de caché
    assert by_name["Alex"]["is_human"] is True and by_name["Alex"]["personality"] is None
    # Personnalités internes : le nom du fichier skill (jamais montré au joueur)
    assert {by_name[n]["personality"] for n in ["marIA", "tobIAs", "mAIsie", "adrIAn", "dIAne"]} == set(PERSONALITIES)
    assert {p["team"] for p in view["players"]} >= {"Démon", "Complice"}


def test_personal_history_of_each_agent(game):
    state, memory = game
    memory.add_public(EventType.PUBLIC_MESSAGE, "p1", "Bonjour le village.")
    view = admin.build_debug_state()

    assert set(view["agent_histories"]) == {"marIA", "tobIAs", "mAIsie", "adrIAn", "dIAne"}
    marIA = view["agent_histories"]["marIA"]
    assert {"role": "Nuit 1 · public · marIA", "content": "Bonjour le village."} in marIA
    assert view["public_history"][-1] == {"moment": "Nuit 1", "sender": "marIA", "content": "Bonjour le village."}


def test_night_actions_of_every_player(game):
    state, memory = game
    record_night_choices(state, {"p1": ("p2",), "h": ("p3",)}, memory)
    view = admin.build_debug_state()

    actions = {(a["player"], a["content"]) for a in view["night_actions"]}
    assert ("marIA", "Nuit 1 : tu as choisi tobIAs.") in actions
    assert ("Alex", "Nuit 1 : tu as choisi mAIsie.") in actions


def test_player_histories_use_names(session):
    session.night_log += [
        NightHistoryEntry(turn=1, type="role_info", info="Tu es le Médium."),
        NightHistoryEntry(turn=2, type="result", dead_player="p1"),
        NightHistoryEntry(turn=3, type="result", dead_player=None),
    ]
    session.vote_log.append(VoteHistoryEntry(turn=1, voter="h", target="p2", executed="p2"))
    session.opened_channels["whisper_h_p1"] = ["h", "p1"]
    view = admin.build_debug_state()

    assert [n["info"] for n in view["night_history"]] == [
        "Tu es le Médium.", "marIA est mort·e cette nuit.", "Personne n'est mort cette nuit."]
    assert view["vote_history"] == [{"turn": 1, "voter": "Alex", "target": "tobIAs", "executed": "tobIAs"}]
    assert view["channels"] == ["Alex, marIA"]


# --- Accès aux routes /admin : réservées au compte admin ----------------------------

ADMIN_URL = "/admin/debug/all-states"


@pytest.fixture
def client(clean_server):
    """Application démarrée (base en mémoire), avec un compte admin et un compte joueur."""
    with TestClient(app) as client:
        with get_session() as db:
            ensure_admin(db, "Gardien", "mot-de-passe-admin")
            register(db, "Vesper", "mot-de-passe-joueur")
        yield client


def log_in(client, pseudo, password):
    assert client.post("/api/auth/login", json={"pseudo": pseudo, "password": password}).status_code == 200


def test_admin_routes_require_a_login(client):
    for method, url in [("get", ADMIN_URL), ("get", "/admin/users"), ("post", "/admin/users/1/reset-password")]:
        response = getattr(client, method)(url)
        assert response.status_code == 401, url
        assert response.json()["detail"] == "Vous n'êtes pas connecté."


def test_player_account_is_forbidden(client):
    log_in(client, "Vesper", "mot-de-passe-joueur")
    response = client.get(ADMIN_URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "Accès réservé à l'administrateur."
    assert client.get("/admin/users").status_code == 403


def test_admin_account_has_access(client):
    log_in(client, "Gardien", "mot-de-passe-admin")
    assert client.get(ADMIN_URL).status_code == 200


def test_forged_cookie_is_refused(client):
    client.cookies.set(COOKIE_NAME, "pas-un-jeton")
    assert client.get(ADMIN_URL).status_code == 401


def test_admin_lists_accounts_without_password_hash(client):
    log_in(client, "Gardien", "mot-de-passe-admin")
    users = client.get("/admin/users").json()
    assert [(u["pseudo"], u["is_admin"]) for u in users] == [("Gardien", True), ("Vesper", False)]
    assert all(set(u) == {"id", "pseudo", "is_admin", "created_at"} for u in users)
    assert all(u["created_at"].endswith("+00:00") for u in users)  # fuseau explicite pour le navigateur


def test_admin_resets_a_player_password(client):
    player = TestClient(app)
    log_in(player, "Vesper", "mot-de-passe-joueur")
    log_in(client, "Gardien", "mot-de-passe-admin")
    vesper = next(u for u in client.get("/admin/users").json() if u["pseudo"] == "Vesper")

    response = client.post(f"/admin/users/{vesper['id']}/reset-password")
    assert response.status_code == 200
    temporary = response.json()["temporary_password"]
    assert response.json()["pseudo"] == "Vesper" and len(temporary) >= 8

    assert player.get("/api/auth/me").status_code == 401  # le joueur est déconnecté
    assert client.post("/api/auth/login", json={"pseudo": "Vesper", "password": "mot-de-passe-joueur"}).status_code == 401
    log_in(TestClient(app), "Vesper", temporary)


def test_admin_password_cannot_be_reset_from_the_panel(client):
    log_in(client, "Gardien", "mot-de-passe-admin")
    admin_id = client.get("/api/auth/me").json()["id"]
    response = client.post(f"/admin/users/{admin_id}/reset-password")
    assert response.status_code == 400
    assert "profil" in response.json()["detail"]


def test_reset_unknown_account(client):
    log_in(client, "Gardien", "mot-de-passe-admin")
    assert client.post("/admin/users/999/reset-password").status_code == 404


def test_unavailable_agents_listed_with_names(session):
    session.agent_failures.append({"turn": 2, "phase": "nuit", "agent": "p1", "step": "night"})
    view = admin.build_debug_state()
    assert view["agent_failures"] == [
        {"moment": "Nuit 2", "agent": "marIA", "step": "action de nuit (choix tiré au hasard)"}]
