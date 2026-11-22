"""Application complète : santé du serveur et WebSocket de bout en bout (connexion, erreurs, chat, refus)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.models import GameState, Player
from backend.rules import get_role
from backend.server import game_runner
from backend.server import websocket_endpoint as ws_module
from backend.server.app import app
from backend.server.connection_manager import manager
from server_helpers import waiting_session


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_manager():
    """Le manager est global : on repart d'une liste de connexions vide à chaque test."""
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


@pytest.fixture(autouse=True)
def no_real_game(monkeypatch, clean_server):
    """Se connecter au WebSocket ne doit pas lancer une vraie partie (et donc de vrais appels LLM).
    Les états par joueur du serveur sont remis à zéro à chaque test."""
    monkeypatch.setattr(game_runner, "ensure_started", lambda player_id, user=None: None)


def waiting_for(player_id: str, kind: str, **request):
    """Simule un moteur qui attend la réponse `kind` du joueur, dans une petite partie (le joueur, ana, agent_1).
    À la connexion, le serveur renvoie le rôle, l'état, puis la demande en attente."""
    players = tuple(Player(id=pid, name=pid.capitalize(), role=get_role("watchman")) for pid in (player_id, "ana", "agent_1"))
    return waiting_session(player_id, kind, GameState(players=players), **request)


def skip_resent_request(ws):
    """À la connexion : accusé, rôle et état de la partie, puis la demande en attente renvoyée."""
    while ws.receive_json()["type"] not in ("action_request", "input_request"):
        pass


# --- /health ------------------------------------------------------------------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


# --- WebSocket /ws/{player_id} ----------------------------------------------------

def test_websocket_registers_and_unregisters_player(client):
    with client.websocket_connect("/ws/humain"):
        assert "humain" in manager.active_connections
    assert "humain" not in manager.active_connections


def test_websocket_invalid_json_returns_error(client):
    with client.websocket_connect("/ws/humain") as ws:
        ws.receive_json()  # accusé "connected"
        ws.send_text("pas du json")
        assert ws.receive_json() == {"type": "error", "data": "Format JSON invalide."}


def test_websocket_invalid_action_returns_error(client):
    with client.websocket_connect("/ws/humain") as ws:
        ws.receive_json()  # accusé "connected"
        ws.send_text(json.dumps({"action": "voler_le_role", "payload": {}}))
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["data"].startswith("Action non valide")


def test_websocket_valid_action_sends_no_error(client):
    waiting_for("humain", "vote", targets=["ana"])
    with client.websocket_connect("/ws/humain") as ws:
        skip_resent_request(ws)
        ws.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": "ana"}}))
        # Une action valide et attendue renvoie une confirmation d'annonce, pas une erreur de parsing
        response = ws.receive_json()
        assert response["type"] == "announcement"

        # On envoie ensuite un message invalide : la première réponse reçue doit être son erreur.
        ws.send_text("pas du json")
        assert ws.receive_json()["data"] == "Format JSON invalide."


def test_websocket_connection_stays_open_after_error(client):
    with client.websocket_connect("/ws/humain") as ws:
        ws.receive_json()  # accusé "connected"
        ws.send_text("pas du json")
        ws.receive_json()
        ws.send_text("toujours pas du json")
        assert ws.receive_json()["type"] == "error"


def test_websocket_public_chat_broadcast(client):
    """Vérifie qu'un message public envoyé par un joueur est bien diffusé à tous."""
    waiting_for("joueur1", "public_message")  # le moteur attend le message public de joueur1
    with client.websocket_connect("/ws/joueur1") as ws1, client.websocket_connect("/ws/joueur2") as ws2:
        skip_resent_request(ws1)
        ws2.receive_json()  # accusé "connected"
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


def test_websocket_public_chat_refused_when_not_asked(client):
    """Le moteur n'attend pas de message public : le message est refusé, et n'est pas diffusé."""
    with client.websocket_connect("/ws/humain") as ws:
        ws.receive_json()  # accusé "connected"
        ws.send_text(json.dumps({"action": "send_chat", "payload": {"channel_id": "public", "content": "Coucou"}}))
        assert ws.receive_json()["type"] == "error"


def test_websocket_request_whisper(client):
    """Vérifie qu'une demande de chuchotement prévient le public puis ouvre le canal privé."""
    waiting_for("humain", "private_partners", choices=["agent_1"])
    with client.websocket_connect("/ws/humain") as ws:
        skip_resent_request(ws)
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


def test_websocket_refused_connection_is_closed_with_reason(client, monkeypatch):
    """Pseudo refusé : la connexion est acceptée puis fermée avec le code 4001 et le motif."""
    from starlette.websockets import WebSocketDisconnect
    monkeypatch.setattr(game_runner, "can_join", lambda player_id, user=None: "Ce pseudo est réservé.")
    with client.websocket_connect("/ws/marIA") as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == ws_module.CLOSE_REFUSED
    assert closed.value.reason == "Ce pseudo est réservé."
    assert "marIA" not in manager.active_connections


def test_websocket_abandon_without_game_returns_error(client, monkeypatch):
    monkeypatch.setattr(game_runner, "abandon_game", lambda player_id: False)
    with client.websocket_connect("/ws/humain") as ws:
        ws.receive_json()  # accusé "connected"
        ws.send_text(json.dumps({"action": "abandon_game", "payload": {}}))
        assert ws.receive_json()["type"] == "error"


def test_websocket_abandon_confirms_to_the_player(client, monkeypatch):
    monkeypatch.setattr(game_runner, "abandon_game", lambda player_id: True)
    waiting_session("humain")  # partie en cours (sans demande en attente)
    with client.websocket_connect("/ws/humain") as ws:
        ws.receive_json()  # accusé "connected"
        ws.send_text(json.dumps({"action": "abandon_game", "payload": {}}))
        assert ws.receive_json() == {"type": "game_abandoned"}
