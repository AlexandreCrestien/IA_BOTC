"""Route d'administration : accès par jeton, et état complet de la partie en cours (rien n'est caché)."""
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
    assert {p["team"] for p in view["players"]} >= {"Démon", "Sbire"}


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
        NightHistoryEntry(turn=1, type="role_info", info="Tu es la Voyante."),
        NightHistoryEntry(turn=2, type="result", dead_player="p1"),
        NightHistoryEntry(turn=3, type="result", dead_player=None),
    ]
    session.vote_log.append(VoteHistoryEntry(turn=1, voter="h", target="p2", executed="p2"))
    session.opened_channels["whisper_h_p1"] = ["h", "p1"]
    view = admin.build_debug_state()

    assert [n["info"] for n in view["night_history"]] == [
        "Tu es la Voyante.", "marIA est mort·e cette nuit.", "Personne n'est mort cette nuit."]
    assert view["vote_history"] == [{"turn": 1, "voter": "Alex", "target": "tobIAs", "executed": "tobIAs"}]
    assert view["channels"] == ["Alex, marIA"]


# --- Accès à la route /admin/debug/all-states --------------------------------------

ADMIN_URL = "/admin/debug/all-states"
TOKEN = "secret-de-test"


@pytest.fixture
def client(clean_server):
    return TestClient(app)


@pytest.fixture
def admin_token(monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_SECRET_TOKEN", TOKEN)
    return TOKEN


def test_admin_with_valid_token(client, admin_token):
    assert client.get(ADMIN_URL, headers={"x-admin-token": admin_token}).status_code == 200


def test_admin_with_wrong_token_is_forbidden(client, admin_token):
    response = client.get(ADMIN_URL, headers={"x-admin-token": "mauvais"})
    assert response.status_code == 403
    assert "Jeton admin invalide" in response.json()["detail"]


def test_admin_without_header_is_forbidden(client, admin_token):
    response = client.get(ADMIN_URL)
    assert response.status_code == 403  # même réponse qu'un jeton faux
    assert "Jeton admin invalide ou manquant" in response.json()["detail"]


def test_admin_with_non_ascii_token_is_forbidden(client, admin_token):
    """Un header avec accent ne doit pas faire planter le serveur (erreur 500)."""
    headers = {"x-admin-token": "jeton-é".encode("latin-1")}
    assert client.get(ADMIN_URL, headers=headers).status_code == 403


def test_admin_with_token_of_different_length_is_forbidden(client, admin_token):
    assert client.get(ADMIN_URL, headers={"x-admin-token": admin_token + "x"}).status_code == 403


def test_admin_is_closed_when_token_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_SECRET_TOKEN", None)
    assert client.get(ADMIN_URL, headers={"x-admin-token": ""}).status_code == 403


def test_admin_is_closed_when_token_is_empty(client, monkeypatch):
    """Un jeton vide (comme dans .env.example) ne doit pas ouvrir l'admin avec un header vide."""
    monkeypatch.setattr(admin, "ADMIN_SECRET_TOKEN", "")
    assert client.get(ADMIN_URL, headers={"x-admin-token": ""}).status_code == 403
