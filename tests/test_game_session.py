"""Partie complète par le WebSocket, comme dans le navigateur, avec de faux agents (aucun appel LLM)."""
import json
import random

import pytest
from fastapi.testclient import TestClient

import backend.server.websockets as websockets
from backend.agent_factory import Agent
from backend.server.app import app
from backend.server.connection_manager import manager
from backend.server.game_session import AI_NAMES, GameSession, player_names


@pytest.fixture(autouse=True)
def fake_agents(monkeypatch):
    """Les agents répondent sans LLM : ils votent tous pour le premier joueur qui n'est pas eux."""
    async def speak_public(self, optional=False):
        return f"Je suis {self.name}."

    async def speak_private(self, partners):
        return "Je te fais confiance."

    async def night_action(self, options, number_of_targets=1):
        return list(options[:number_of_targets])

    async def vote(self, options):
        return next(name for name in options if name != self.name)

    for name, fn in [("speak_public", speak_public), ("speak_private", speak_private),
                     ("night_action", night_action), ("vote", vote)]:
        monkeypatch.setattr(Agent, name, fn)
    # Partie reproductible
    monkeypatch.setattr(websockets, "session_factory",
                        lambda pseudo, send: GameSession(pseudo, send, rng=random.Random(4)))
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


def answer(request, private_messages_sent):
    """Réponse automatique de l'humain à une demande du moteur."""
    kind = request["kind"]
    if kind == "night":
        return {"action": "night_action", "payload": {"targets": [o["id"] for o in request["options"][:request["count"]]]}}
    if kind == "public_message":
        return {"action": "send_chat", "payload": {"channel_id": "public", "content": "Bonjour à tous."}}
    if kind == "private_partners":
        return {"action": "pass", "payload": {}}  # un agent doit venir nous parler
    if kind == "private_message":
        if private_messages_sent[0] == 0:
            private_messages_sent[0] += 1
            return {"action": "send_chat", "payload": {"channel_id": "private", "content": "Qui soupçonnes-tu ?"}}
        return {"action": "pass", "payload": {}}
    if kind == "vote":
        return {"action": "vote", "payload": {"target_id": None}}
    raise AssertionError(f"demande inconnue : {kind}")


def play_full_game():
    received = []
    with TestClient(app).websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        for _ in range(3000):
            message = ws.receive_json()
            received.append(message)
            if message["type"] == "game_over":
                return received
            if message["type"] == "request":
                sent = [0]
                if message["data"]["kind"] == "private_message":
                    sent = [sum(1 for m in received if m["type"] == "event" and m["data"]["is_me"]
                                and m["data"]["channel"] == "private")]
                ws.send_text(json.dumps(answer(message["data"], sent)))
    raise AssertionError("la partie ne s'est pas terminée")


def test_full_game_ends_with_all_roles_revealed():
    received = play_full_game()
    errors = [m for m in received if m["type"] == "error"]
    assert errors == []
    game_over = received[-1]["data"]
    assert len(game_over["roles"]) == 6
    assert game_over["winner"]


def test_human_receives_role_announcements_and_messages():
    received = play_full_game()
    states = [m["data"] for m in received if m["type"] == "state"]
    assert states[0]["me"]["name"] == "Sasha" and states[0]["me"]["role"]
    events = [m["data"] for m in received if m["type"] == "event"]
    contents = [e["content"] for e in events]
    assert any(c.startswith("Le jour 1 se lève") for c in contents)
    assert any(c.startswith("Votes :") for c in contents)
    assert any(e["channel"] == "public" and not e["is_game_master"] and not e["is_me"] for e in events)
    assert any(e["is_me"] and e["content"] == "Bonjour à tous." for e in events)


def test_agent_comes_to_talk_when_human_chooses_nobody():
    received = play_full_game()
    private = [m["data"] for m in received if m["type"] == "event" and m["data"]["channel"] == "private"]
    assert private, "aucune conversation privée"
    assert not private[0]["is_me"]  # l'agent parle en premier
    assert any(p["is_me"] and p["content"] == "Qui soupçonnes-tu ?" for p in private)


def test_human_never_sees_private_events_of_others():
    received = play_full_game()
    for m in received:
        if m["type"] == "event" and m["data"]["channel"] in ("private", "personal"):
            assert m["data"]["channel"] == "personal" or "Sasha" in m["data"]["participants"]


def test_wrong_action_for_the_request_is_refused():
    with TestClient(app).websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        while True:
            message = ws.receive_json()
            if message["type"] == "request":
                break
        ws.send_text(json.dumps({"action": "create_channel", "payload": {"target_ids": ["ia1"]}}))
        while True:
            message = ws.receive_json()
            if message["type"] == "error":
                assert "Action inattendue" in message["data"]
                return


def test_human_name_cannot_be_an_ai_name():
    names = player_names(AI_NAMES[0])
    assert len(set(names.values())) == 6
