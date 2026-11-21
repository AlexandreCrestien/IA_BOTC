"""ConnectionManager : connexions WebSocket des joueurs, envoi ciblé et diffusion (sans vrai réseau)."""
import asyncio
import json

from backend.server.connection_manager import ConnectionManager

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


def test_disconnect_of_an_old_connection_keeps_the_new_one():
    """Rechargement ou second onglet : fermer l'ancienne connexion ne doit pas couper la nouvelle."""
    cm, old, new = ConnectionManager(), FakeWebSocket(), FakeWebSocket()
    asyncio.run(cm.connect("humain", old))
    asyncio.run(cm.connect("humain", new))
    cm.disconnect("humain", old)
    assert cm.active_connections == {"humain": new}
    cm.disconnect("humain", new)
    assert cm.active_connections == {}


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
