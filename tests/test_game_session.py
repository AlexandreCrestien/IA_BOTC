"""Partie complète par le WebSocket, comme dans le navigateur, avec de faux agents (aucun appel LLM)."""
import json
import random

import pytest
from fastapi.testclient import TestClient

import backend.human_turns as human_turns
import backend.server.websockets as websockets
from backend.agent_factory import Agent
from backend.memory_manager import game_master
from backend.models import EventType
from backend.server.app import app
from backend.server.connection_manager import manager
from backend.server.game_session import AI_NAMES, GameSession, player_names

SETTINGS = {"day_seconds": 60, "nominate": True}


@pytest.fixture(autouse=True)
def fake_agents(monkeypatch):
    """Les agents répondent sans LLM. Ils désignent le premier joueur proposé et votent pour."""
    async def speak_public(self, optional=False):
        return f"Je suis {self.name}."

    async def speak_private(self, partners):
        return "Je te fais confiance."

    async def night_action(self, options, number_of_targets=1):
        return list(options[:number_of_targets])

    async def nominate(self, options):
        return options[0] if SETTINGS["nominate"] else None

    async def vote_on(self, nominee):
        return True

    async def vote(self, options):
        return next(name for name in options if name != self.name)

    for name, fn in [("speak_public", speak_public), ("speak_private", speak_private),
                     ("night_action", night_action), ("nominate", nominate), ("vote_on", vote_on),
                     ("vote", vote)]:
        monkeypatch.setattr(Agent, name, fn)

    async def no_llm(*args, **kwargs):
        raise AssertionError("appel LLM réel pendant un test")

    import backend.llm_client as llm_client
    monkeypatch.setattr(llm_client, "ask_llm", no_llm)  # garde-fou : aucun appel réseau

    async def simulate(agents, memory):
        names = ", ".join(agent.name for agent in agents)
        memory.add_public(EventType.private_meeting, game_master, f"Conversation privée entre {names}.")
        return []

    monkeypatch.setattr(human_turns, "simulate_agents_conversation", simulate)
    SETTINGS.update(day_seconds=60, nominate=True)
    monkeypatch.setattr(websockets, "session_factory",
                        lambda pseudo, send: GameSession(pseudo, send, rng=random.Random(4),
                                                         day_seconds=SETTINGS["day_seconds"]))
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


class AutoHuman:
    """Répond automatiquement aux demandes : chaque jour, un message public, une conversation privée
    (un message), puis la fin de sa journée. Vote toujours pour."""

    def __init__(self):
        self.day_step = 0
        self.private_sent = False
        self.turn = None

    def answer(self, request, turn):
        if turn != self.turn:
            self.turn, self.day_step = turn, 0
        kind = request["kind"]
        if kind == "night":
            targets = [o["id"] for o in request["options"][:request["count"]]]
            return {"action": "night_action", "payload": {"targets": targets}}
        if kind == "day":
            self.day_step += 1
            if self.day_step == 1:
                return {"action": "send_chat", "payload": {"channel_id": "public", "content": "Bonjour à tous."}}
            if self.day_step == 2:
                self.private_sent = False
                return {"action": "create_channel", "payload": {"target_ids": [request["options"][0]["id"]]}}
            return {"action": "pass", "payload": {}}
        if kind == "private_message":
            if not self.private_sent:
                self.private_sent = True
                return {"action": "send_chat", "payload": {"channel_id": "private", "content": "Qui soupçonnes-tu ?"}}
            return {"action": "pass", "payload": {}}
        if kind == "vote":
            return {"action": "vote", "payload": {"target_id": request["options"][0]["id"]}}
        if kind == "final_vote":
            return {"action": "vote", "payload": {"target_id": request["options"][-1]["id"]}}
        raise AssertionError(f"demande inconnue : {kind}")


def play_full_game(human=None):
    human = human or AutoHuman()
    received, turn = [], 1
    with TestClient(app).websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        for _ in range(5000):
            message = ws.receive_json()
            received.append(message)
            if message["type"] == "state":
                turn = message["data"]["turn"]
            if message["type"] == "game_over":
                return received
            if message["type"] == "request":
                ws.send_text(json.dumps(human.answer(message["data"], turn)))
    raise AssertionError("la partie ne s'est pas terminée")


def events(received):
    return [m["data"] for m in received if m["type"] == "event"]


def test_full_game_ends_with_all_roles_revealed():
    received = play_full_game()
    assert [m for m in received if m["type"] == "error"] == []
    game_over = received[-1]["data"]
    assert len(game_over["roles"]) == 6
    assert game_over["winner"]


def test_day_request_has_timer_and_options():
    received = play_full_game()
    day = next(m["data"] for m in received if m["type"] == "request" and m["data"]["kind"] == "day")
    assert day["deadline"] > 0
    assert len(day["options"]) == 5 and day["can_nominate"] is True
    assert len(day["nominee_options"]) == 5


def test_human_receives_announcements_nominations_and_votes():
    received = play_full_game()
    contents = [e["content"] for e in events(received)]
    assert any(c.startswith("Le jour 1 se lève") for c in contents)
    assert any(e["kind"] == "nomination" for e in events(received))
    assert any(c.startswith("Vote sur ") for c in contents)
    assert any(e["is_me"] and e["content"] == "Bonjour à tous." for e in events(received))


def test_ais_answer_the_human_public_message():
    received = play_full_game()
    evs = events(received)
    mine = next(i for i, e in enumerate(evs) if e["is_me"] and e["content"] == "Bonjour à tous.")
    assert any(e["channel"] == "public" and not e["is_me"] and not e["is_game_master"] for e in evs[mine + 1:])


def test_private_conversation_and_parallel_one_for_the_others():
    received = play_full_game()
    private = [e for e in events(received) if e["channel"] == "private"]
    assert any(p["is_me"] and p["content"] == "Qui soupçonnes-tu ?" for p in private)
    assert any(not p["is_me"] for p in private)
    meetings = [e["content"] for e in events(received) if e["kind"] == "private_meeting"]
    assert any("Sasha" in m for m in meetings)          # la nôtre
    assert any("Sasha" not in m for m in meetings)      # celle des autres agents, en parallèle


def test_private_request_names_participants_when_human_chooses():
    received = play_full_game()
    request = next(m["data"] for m in received if m["type"] == "request" and m["data"]["kind"] == "private_message")
    assert "Sasha" in request["participants"] and len(request["participants"]) == 2


def test_human_never_sees_private_events_of_others():
    for e in events(play_full_game()):
        if e["channel"] == "private":
            assert "Sasha" in e["participants"]


class NominatingHuman(AutoHuman):
    """Désigne directement le premier joueur proposé."""

    def answer(self, request, turn):
        if request["kind"] == "day" and request["can_nominate"]:
            return {"action": "nominate", "payload": {"target_id": request["nominee_options"][0]["id"]}}
        return super().answer(request, turn)


def test_human_nomination_starts_the_vote():
    received = play_full_game(NominatingHuman())
    nominations = [e for e in events(received) if e["kind"] == "nomination"]
    assert nominations and nominations[0]["is_me"]


def test_without_nomination_everyone_votes_at_the_end_of_the_day():
    """Les IA ne désignent personne et l'humain ne fait rien : à la fin du temps, vote de fin de jour.
    À la moitié du temps, un agent propose une conversation privée."""
    SETTINGS.update(day_seconds=0.6, nominate=False)
    received = []
    with TestClient(app).websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        for _ in range(2000):
            message = ws.receive_json()
            received.append(message)
            if message["type"] == "request" and message["data"]["kind"] == "night":
                ws.send_text(json.dumps({"action": "pass", "payload": {}}))
            if message["type"] == "request" and message["data"]["kind"] == "final_vote":
                break
    proposals = [m["data"]["proposal"] for m in received
                 if m["type"] == "request" and m["data"]["kind"] == "day" and m["data"]["proposal"]]
    assert proposals, "aucun agent n'a proposé de conversation"
    assert not any(e["kind"] == "nomination" for e in events(received))
    assert any(e["content"].startswith("Fin du jour") for e in events(received))


def test_accepting_a_proposal_lets_the_agent_speak_first():
    SETTINGS.update(day_seconds=0.6, nominate=False)
    received = []
    with TestClient(app).websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        for _ in range(2000):
            message = ws.receive_json()
            received.append(message)
            if message["type"] != "request":
                continue
            request = message["data"]
            if request["kind"] == "night":
                ws.send_text(json.dumps({"action": "pass", "payload": {}}))
            elif request["kind"] == "day" and request["proposal"]:
                ws.send_text(json.dumps({"action": "create_channel",
                                         "payload": {"target_ids": [request["proposal"]["id"]]}}))
            elif request["kind"] == "private_message":
                break
    private = [e for e in events(received) if e["channel"] == "private"]
    assert private and not private[0]["is_me"]


def test_wrong_action_during_the_day_is_refused():
    with TestClient(app).websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        while True:
            message = ws.receive_json()
            if message["type"] == "request" and message["data"]["kind"] == "night":
                ws.send_text(json.dumps({"action": "pass", "payload": {}}))
            if message["type"] == "request" and message["data"]["kind"] == "day":
                break
        ws.send_text(json.dumps({"action": "night_action", "payload": {"targets": []}}))
        while True:
            message = ws.receive_json()
            if message["type"] == "error":
                assert "Action inattendue" in message["data"]
                return


def test_human_name_cannot_be_an_ai_name():
    names = player_names(AI_NAMES[0])
    assert len(set(names.values())) == 6


def test_admin_route_shows_hidden_information_of_running_games(monkeypatch):
    import backend.server.admin as admin
    monkeypatch.setattr(admin, "ADMIN_SECRET_TOKEN", "jeton")
    client = TestClient(app)
    with client.websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        while True:
            message = ws.receive_json()
            if message["type"] == "request":
                break
        response = client.get("/admin/debug/all-states", headers={"x-admin-token": "jeton"})
    assert response.status_code == 200
    [game] = response.json()["games"]
    assert game["player"] == "Sasha"
    assert len(game["players"]) == 6
    assert all(p["role"] for p in game["players"])
    assert {p["personality"] for p in game["players"]} >= {"humain", "agitator"}
    assert any(e["visible_to"] != "tous" for e in game["events"])  # infos secrètes visibles par l'admin


def test_admin_route_lists_no_game_after_disconnect(monkeypatch):
    import backend.server.admin as admin
    monkeypatch.setattr(admin, "ADMIN_SECRET_TOKEN", "jeton")
    client = TestClient(app)
    with client.websocket_connect("/ws/Sasha") as ws:
        ws.send_text(json.dumps({"action": "start_game"}))
        ws.receive_json()
    assert client.get("/admin/debug/all-states", headers={"x-admin-token": "jeton"}).json()["games"] == []


class DoubleNominatingHuman(AutoHuman):
    """Essaie de désigner deux fois dans la même journée."""

    def __init__(self):
        super().__init__()
        self.tries = 0

    def answer(self, request, turn):
        if request["kind"] == "day" and self.tries < 2:
            self.tries += 1
            return {"action": "nominate", "payload": {"target_id": request["options"][0]["id"]}}
        return super().answer(request, turn)


def test_human_cannot_nominate_twice_the_same_day():
    SETTINGS.update(nominate=False, day_seconds=1.0)  # après le refus, on laisse filer le temps

    async def vote_on(self, nominee):
        return False  # la désignation échoue : le jour continue
    import pytest as _pytest
    mp = _pytest.MonkeyPatch()
    mp.setattr(Agent, "vote_on", vote_on)
    try:
        received = play_full_game(DoubleNominatingHuman())
    finally:
        mp.undo()
    day_requests = [m["data"] for m in received if m["type"] == "request" and m["data"]["kind"] == "day"]
    assert day_requests[0]["can_nominate"] is True
    assert day_requests[1]["can_nominate"] is False  # même jour, après sa désignation
    errors = [m["data"] for m in received if m["type"] == "error"]
    assert any("désigner" in e for e in errors)
    assert any(e["content"].startswith("Fin du jour") for e in events(received))
