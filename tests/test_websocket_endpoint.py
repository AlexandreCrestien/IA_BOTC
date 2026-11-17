import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.human_port import QueueHumanPort
from backend.server import websockets as ws


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(ws.router)
    return TestClient(app)


def setup_function():
    ws.ports.clear()
    ws.pending.clear()
    ws.whispers.clear()


def test_vote_vide_arrive_comme_none():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": ""}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "announcement"
    assert port.answers.get_nowait() is None


def test_vote_avec_cible_arrive_telle_quelle():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": "imp"}}))
        conn.receive_text()

    assert port.answers.get_nowait() == "imp"


def test_vote_hors_phase_est_refuse():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "night_choice"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"target_id": "imp"}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "error"
    assert port.answers.empty()


def test_action_de_nuit_arrive_en_tuple():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "night_choice"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.send_text(json.dumps({"action": "submit_night_action", "payload": {"targets": ["imp"]}}))
        conn.receive_text()

    assert port.answers.get_nowait() == ("imp",)


def test_champ_inconnu_est_refuse():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.send_text(json.dumps({"action": "submit_vote", "payload": {"targt_id": "imp"}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "error"
    assert port.answers.empty()


def test_whisper_ouvre_le_salon_et_repond_au_moteur():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "private_partners"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.send_text(json.dumps({"action": "request_whisper", "payload": {"targets": ["imp"]}}))
        first = json.loads(conn.receive_text())
        second = json.loads(conn.receive_text())

    assert first["sender"] == "Grimoire"
    assert second["type"] == "private_channel_opened"
    assert second["channel_id"] == "whisper_h_imp"
    assert ws.whispers["h"] == "whisper_h_imp"
    assert port.answers.get_nowait() == ["imp"]