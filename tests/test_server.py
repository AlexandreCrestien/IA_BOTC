import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

import backend.server.admin as admin
from backend.server.app import app
from backend.server.connection_manager import ConnectionManager, manager
from backend.server.schemas import (
    ClientActionPacket,
    RequestWhisperAction,
    RespondWhisperInvitationAction,
    SubmitNightAction,
    SubmitVoteAction,
    TriggerVotePhaseAction,
    SendChatAction,
)

ADMIN_URL = "/admin/debug/all-states"
TOKEN = "secret-de-test"
parse_action = TypeAdapter(ClientActionPacket).validate_python


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_manager():
    """Le manager est global : on repart d'une liste de connexions vide à chaque test."""
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


@pytest.fixture
def admin_token(monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_SECRET_TOKEN", TOKEN)
    return TOKEN


# --- /health ------------------------------------------------------------------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


# --- /admin -------------------------------------------------------------------

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


# --- Schémas des actions du client -----------------------------------------------

def test_parse_send_chat():
    action = parse_action({"action": "send_chat", "payload": {"channel_id": "public", "content": "Salut"}})
    assert isinstance(action, SendChatAction)
    assert action.payload.content == "Salut"


@pytest.mark.parametrize("targets", [["ana"], ["ana", "bruno"]])
def test_parse_request_whisper_with_one_or_two_agents(targets):
    action = parse_action({"action": "request_whisper", "payload": {"targets": targets}})
    assert isinstance(action, RequestWhisperAction)
    assert action.payload.targets == targets


@pytest.mark.parametrize("targets", [[], ["ana", "bruno", "carla"]])
def test_request_whisper_needs_one_or_two_agents(targets):
    with pytest.raises(ValidationError):
        parse_action({"action": "request_whisper", "payload": {"targets": targets}})


def test_parse_respond_whisper_invitation():
    action = parse_action({"action": "respond_whisper_invitation", "payload": {"target_agent_id": "tobIAs", "accepted": True}})
    assert isinstance(action, RespondWhisperInvitationAction)
    assert action.payload.target_agent_id == "tobIAs"
    assert action.payload.accepted is True


def test_parse_submit_night_action():
    action = parse_action({"action": "submit_night_action", "payload": {"targets": ["ana", "bruno"]}})
    assert isinstance(action, SubmitNightAction)
    assert action.payload.targets == ["ana", "bruno"]


def test_submit_night_action_targets_default_to_empty():
    assert parse_action({"action": "submit_night_action", "payload": {}}).payload.targets == []


def test_parse_vote_for_player():
    action = parse_action({"action": "submit_vote", "payload": {"target_id": "ana"}})
    assert isinstance(action, SubmitVoteAction)
    assert action.payload.target_id == "ana"


def test_vote_for_nobody():
    assert parse_action({"action": "submit_vote", "payload": {"target_id": None}}).payload.target_id is None
    assert parse_action({"action": "submit_vote", "payload": {}}).payload.target_id is None


def test_parse_trigger_vote_phase():
    action = parse_action({"action": "trigger_vote_phase", "payload": {}})
    assert isinstance(action, TriggerVotePhaseAction)


def test_empty_chat_message_is_rejected():
    with pytest.raises(ValidationError):
        parse_action({"action": "send_chat", "payload": {"channel_id": "public", "content": ""}})


@pytest.mark.parametrize("packet", [
    {"action": "voler_le_role", "payload": {}},   # action inconnue
    {"action": "send_chat"},                      # payload manquant
])
def test_invalid_packets_are_rejected(packet):
    with pytest.raises(ValidationError):
        parse_action(packet)


def test_packet_without_action_is_rejected():
    """Sans "action", le paquet ne doit pas être deviné d'après son contenu."""
    with pytest.raises(ValidationError):
        parse_action({"payload": {"target_id": "ana"}})


def test_unknown_payload_field_is_rejected():
    """Une faute de frappe ('targets' au lieu de 'target_id') ne doit pas devenir un vote pour personne."""
    with pytest.raises(ValidationError):
        parse_action({"action": "submit_vote", "payload": {"targets": ["ana"]}})


def test_unknown_field_in_action_is_rejected():
    with pytest.raises(ValidationError):
        parse_action({"action": "submit_vote", "payload": {"target_id": "ana"}, "joueur": "ana"})


# --- WebSocket /ws/{player_id} ----------------------------------------------------

def test_websocket_registers_and_unregisters_player(client):
    with client.websocket_connect("/ws/humain"):
        assert "humain" in manager.active_connections
    assert "humain" not in manager.active_connections


def test_websocket_invalid_json_returns_error(client):
    with client.websocket_connect("/ws/humain") as ws:
        ws.send_text("pas du json")
        assert ws.receive_json() == {"type": "error", "data": "Format JSON invalide."}


def test_websocket_invalid_action_returns_error(client):
    with client.websocket_connect("/ws/humain") as ws:
        ws.send_text(json.dumps({"action": "voler_le_role", "payload": {}}))
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["data"].startswith("Action non valide")


def test_websocket_valid_action_sends_no_error(client):
    with client.websocket_connect("/ws/humain") as ws:
        ws.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": "ana"}}))
        # Une action valide renvoie une confirmation d'annonce, on vérifie que ce n'est pas une erreur de parsing
        response = ws.receive_json()
        assert response["type"] == "announcement"
        
        # On envoie ensuite un message invalide : la première réponse reçue doit être son erreur.
        ws.send_text("pas du json")
        assert ws.receive_json()["data"] == "Format JSON invalide."


def test_websocket_connection_stays_open_after_error(client):
    with client.websocket_connect("/ws/humain") as ws:
        ws.send_text("pas du json")
        ws.receive_json()
        ws.send_text("toujours pas du json")
        assert ws.receive_json()["type"] == "error"


# --- ConnectionManager (sans vrai réseau) ----------------------------------------

class FakeWebSocket:
    def __init__(self, fail: bool = False):
        self.accepted = False
        self.sent: list[dict] = []
        self.fail = fail

    async def accept(self):
        self.accepted = True

    async def send_text(self, text: str):
        if self.fail:
            raise RuntimeError("connexion coupée")
        self.sent.append(json.loads(text))


def test_connect_accepts_and_registers():
    cm, ws = ConnectionManager(), FakeWebSocket()
    asyncio.run(cm.connect("humain", ws))
    assert ws.accepted
    assert cm.active_connections == {"humain": ws}


def test_disconnect_unknown_player_does_nothing():
    cm = ConnectionManager()
    cm.disconnect("fantome")
    assert cm.active_connections == {}


def test_send_to_player_sends_json():
    cm, ws = ConnectionManager(), FakeWebSocket()
    asyncio.run(cm.connect("humain", ws))
    asyncio.run(cm.send_to_player("humain", {"type": "chat_message", "data": "Bonjour"}))
    assert ws.sent == [{"type": "chat_message", "data": "Bonjour"}]


def test_send_to_unknown_player_does_not_crash():
    asyncio.run(ConnectionManager().send_to_player("fantome", {"type": "error", "data": "x"}))


def test_send_failure_disconnects_player():
    cm = ConnectionManager()
    asyncio.run(cm.connect("humain", FakeWebSocket(fail=True)))
    asyncio.run(cm.send_to_player("humain", {"type": "error", "data": "x"}))
    assert "humain" not in cm.active_connections


def test_broadcast_reaches_everyone():
    cm, ws1, ws2 = ConnectionManager(), FakeWebSocket(), FakeWebSocket()
    asyncio.run(cm.connect("a", ws1))
    asyncio.run(cm.connect("b", ws2))
    asyncio.run(cm.broadcast({"type": "state_update", "data": {}}))
    assert ws1.sent == ws2.sent == [{"type": "state_update", "data": {}}]


def test_broadcast_removes_broken_connections_and_keeps_others():
    cm, ok = ConnectionManager(), FakeWebSocket()
    asyncio.run(cm.connect("ok", ok))
    asyncio.run(cm.connect("coupe", FakeWebSocket(fail=True)))
    asyncio.run(cm.broadcast({"type": "state_update", "data": {}}))
    assert list(cm.active_connections) == ["ok"]
    assert ok.sent == [{"type": "state_update", "data": {}}]


def test_broadcast_without_connections_does_nothing():
    asyncio.run(ConnectionManager().broadcast({"type": "state_update", "data": {}}))


def test_websocket_public_chat_broadcast(client):
    """Vérifie qu'un message public envoyé par un joueur est bien diffusé à tous."""
    with client.websocket_connect("/ws/joueur1") as ws1, client.websocket_connect("/ws/joueur2") as ws2:
        # Le joueur 1 envoie un message public
        ws1.send_text(json.dumps({
            "action": "send_chat",
            "payload": {"channel_id": "public", "content": "Bonjour le village"}
        }))
        
        # Les deux joueurs doivent recevoir le message de chat
        msg1 = ws1.receive_json()
        msg2 = ws2.receive_json()
        
        assert msg1["type"] == "chat"
        assert msg1["content"] == "Bonjour le village"
        assert msg1["sender"] == "joueur1"
        
        assert msg2 == msg1


def test_websocket_request_whisper(client):
    """Vérifie qu'une demande de chuchotement prévient le public puis ouvre le canal privé."""
    with client.websocket_connect("/ws/humain") as ws:
        ws.send_text(json.dumps({
            "action": "request_whisper",
            "payload": {"targets": ["agent_1"]}
        }))
        
        # 1. Le premier message est l'annonce publique dans le chat
        public_msg = ws.receive_json()
        assert public_msg["type"] == "chat"
        assert public_msg["channel_id"] == "public"
        
        # 2. Le second message est l'ouverture effective du canal privé
        private_msg = ws.receive_json()
        assert private_msg["type"] == "private_channel_opened"
        assert "agent_1" in private_msg["members"]
        assert private_msg["channel_id"].startswith("whisper_")


def test_websocket_trigger_vote_phase(client):
    """Vérifie que déclencher le vote diffuse bien l'information à tout le monde."""
    with client.websocket_connect("/ws/humain") as ws:
        ws.send_text(json.dumps({
            "action": "trigger_vote_phase",
            "payload": {}
        }))
        
        response = ws.receive_json()
        assert response["type"] == "phase_update"
        assert response["phase"] == "vote"