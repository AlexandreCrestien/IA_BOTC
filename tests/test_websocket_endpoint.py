import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.human_port import QueueHumanPort
from backend.server import game_runner
from backend.server import websockets as ws


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(ws.router)
    return TestClient(app)


def setup_function():
    ws.ports.clear()
    ws.pending.clear()
    ws.current_request.clear()
    ws.whispers.clear()
    ws.whisper_left.clear()
    ws.chat_log.clear()
    ws.opened_channels.clear()
    ws.known_allies.clear()
    ws.roles_sent.clear()


@pytest.fixture(autouse=True)
def no_real_game(monkeypatch):
    """Se connecter ne doit pas lancer une vraie partie : le port est fourni par chaque test."""
    monkeypatch.setattr(game_runner, "ensure_started", lambda player_id: None)


def test_vote_vide_arrive_comme_none():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": ""}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "announcement"
    assert port.answers.get_nowait() is None


def test_vote_avec_cible_arrive_telle_quelle():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": "imp"}}))
        conn.receive_text()

    assert port.answers.get_nowait() == "imp"


def test_vote_hors_phase_est_refuse():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "night_choice"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": "imp"}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "error"
    assert port.answers.empty()


def test_action_de_nuit_arrive_en_tuple():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "night_choice"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "submit_night_action", "payload": {"targets": ["imp"]}}))
        conn.receive_text()

    assert port.answers.get_nowait() == ("imp",)


def test_champ_inconnu_est_refuse():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"targt_id": "imp"}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "error"
    assert port.answers.empty()


def test_whisper_ouvre_le_salon_et_repond_au_moteur():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "private_partners"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "request_whisper", "payload": {"targets": ["imp"]}}))
        first = json.loads(conn.receive_text())
        second = json.loads(conn.receive_text())

    assert first["sender"] == "Grimoire"
    assert second["type"] == "private_channel_opened"
    assert second["channel_id"] == "whisper_h_imp"
    assert ws.whispers["h"] == "whisper_h_imp"
    assert port.answers.get_nowait() == ["imp"]

# --- Point 2 : reprise après rechargement -----------------------------------

def test_reconnexion_rouvre_le_salon_et_renvoie_l_historique_du_chat():
    port = QueueHumanPort()
    ws.ports["h"] = port
    client = make_client()

    # Première connexion : le joueur ouvre un salon puis y écrit
    ws.pending["h"] = "private_partners"
    with client.websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "request_whisper", "payload": {"targets": ["imp"]}}))
        conn.receive_text()  # annonce publique du Grimoire
        conn.receive_text()  # salon ouvert
        ws.pending["h"] = "private_message"
        conn.send_text(json.dumps({"action": "send_chat", "payload": {"channel_id": "whisper_h_imp", "content": "Psst"}}))
        conn.receive_text()  # écho du message privé

    # Rechargement : le salon et les messages reviennent, sans placer le joueur dans le salon
    with client.websocket_connect("/ws/h") as conn:
        messages = [json.loads(conn.receive_text()) for _ in range(4)]

    assert messages[0] == {"type": "connected"}
    assert messages[1] == {"type": "private_channel_opened", "channel_id": "whisper_h_imp",
                           "members": ["h", "imp"], "text": "", "focus": False}
    assert messages[2]["channel_id"] == "public" and messages[2]["sender"] == "Grimoire"
    assert messages[3] == {"type": "chat", "channel_id": "whisper_h_imp", "sender": "h", "content": "Psst"}


def test_les_allies_reveles_sont_renvoyes_avec_le_role():
    from backend.models import GameState, Player
    from backend.models.enums import Equipe, Phase
    from backend.models.role import Role

    imp = Role(name_FR="Diablotin", name_EN="imp", team=Equipe.DEMON, phase=Phase.NUIT)
    poisoner = Role(name_FR="Empoisonneur", name_EN="poisoner", team=Equipe.SBIRE, phase=Phase.NUIT)
    port = QueueHumanPort()
    port.state = GameState(turn=2, phase=Phase.NUIT, players=(
        Player(id="h", name="Alex", role=imp), Player(id="p1", name="marIA", role=poisoner),
    ))
    ws.ports["h"] = port
    sent = []

    async def fake_send(player_id, message):
        sent.append(message)

    async def scenario():
        # La révélation de la première nuit est retenue…
        await ws._send_request("h", port, "night_info",
                               {"turn": 1, "info": "Ton allié est marIA.", "allies": [{"id": "p1", "role": "Empoisonneur"}]})
        # …et renvoyée avec le rôle à la reconnexion
        ws.roles_sent.discard("h")
        await ws._send_state("h", port)

    original = ws.manager.send_to_player
    ws.manager.send_to_player = fake_send
    try:
        asyncio.run(scenario())
    finally:
        ws.manager.send_to_player = original

    role = next(m for m in sent if m["type"] == "role_assigned")
    assert role["allies"] == [{"id": "p1", "role": "Empoisonneur"}]


# --- Point 3 : étapes facultatives ------------------------------------------

def _sync(conn):
    """Attend que le serveur ait traité les messages précédents (il répond à un JSON invalide)."""
    conn.send_text("pas du json")
    assert json.loads(conn.receive_text())["type"] == "error"


def test_passer_son_message_public():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "public_message"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "skip_turn", "payload": {"kind": "public_message"}}))
        _sync(conn)

    assert port.answers.get_nowait() is None
    assert "h" not in ws.pending


def test_terminer_la_discussion_privee_avant_trois_messages():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "private_message"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "skip_turn", "payload": {"kind": "private_message"}}))
        _sync(conn)

    assert port.answers.get_nowait() is None


def test_passer_au_vote_sans_salon_prive():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "private_partners"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "skip_turn", "payload": {"kind": "private_partners"}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "announcement"
    assert port.answers.get_nowait() == []  # « personne » pour le moteur


def test_passer_une_etape_qui_n_est_pas_attendue_est_refuse():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "skip_turn", "payload": {"kind": "public_message"}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "error"
    assert port.answers.empty()
    assert ws.pending["h"] == "vote"


def test_le_vote_ne_peut_pas_etre_passe_par_skip_turn():
    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "skip_turn", "payload": {"kind": "vote"}}))
        assert json.loads(conn.receive_text())["data"].startswith("Action non valide")


def test_saisie_attendue_annoncee_au_front():
    sent = []

    async def fake_send(player_id, message):
        sent.append(message)

    async def scenario():
        port = QueueHumanPort()
        ws.whispers["h"] = "whisper_h_imp"
        ws.whisper_left["h"] = 2
        await ws._send_request("h", port, "public_message", {"kind": "public_message"})
        await ws._send_request("h", port, "private_message", {"kind": "private_message"})

    original = ws.manager.send_to_player
    ws.manager.send_to_player = fake_send
    try:
        asyncio.run(scenario())
    finally:
        ws.manager.send_to_player = original

    assert sent[0]["type"] == "input_request" and sent[0]["kind"] == "public_message"
    assert sent[0]["channel_id"] == "public"
    assert sent[1] == {"type": "input_request", "kind": "private_message", "channel_id": "whisper_h_imp",
                       "left": 2, "text": "Il vous reste 2 message(s) privé(s) avec vos interlocuteurs."}
