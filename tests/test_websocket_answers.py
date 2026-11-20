import asyncio

from backend.human_port import QueueHumanPort
from backend.server import websockets as ws


def setup_function():
    ws.ports.clear()
    ws.pending.clear()
    ws.current_request.clear()
    ws.whispers.clear()
    ws.chat_log.clear()
    ws.opened_channels.clear()
    ws.known_allies.clear()


def test_reponse_acceptee_pour_la_demande_attendue():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "vote"

    assert ws._answer("h", "vote", None) is True
    assert port.answers.get_nowait() is None
    assert "h" not in ws.pending


def test_reponse_refusee_pour_une_autre_demande():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "night_choice"

    assert ws._answer("h", "vote", "imp") is False
    assert port.answers.empty()
    assert ws.pending["h"] == "night_choice"


def test_reponse_refusee_sans_partie():
    assert ws._answer("inconnu", "vote", "imp") is False


def test_une_seule_reponse_par_demande():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "public_message"

    assert ws._answer("h", "public_message", "bonjour") is True
    assert ws._answer("h", "public_message", "encore") is False
    assert port.answers.get_nowait() == "bonjour"
    assert port.answers.empty()


def test_forward_retient_la_demande_et_l_envoie(monkeypatch):
    sent = []

    async def fake_send(player_id, message):
        sent.append((player_id, message))

    monkeypatch.setattr(ws.manager, "send_to_player", fake_send)

    async def scenario():
        port = QueueHumanPort()
        task = asyncio.create_task(ws._forward_requests("h", port))

        await port.requests.put({"kind": "vote", "targets": ["imp", "h"]})
        await asyncio.sleep(0.01)
        assert ws.pending.get("h") == "vote"

        # Une simple information (message public d'une IA) n'attend pas de réponse
        await port.requests.put({"kind": "public_chat", "author": "imp", "text": "Bonjour"})
        await asyncio.sleep(0.01)
        assert "h" not in ws.pending

        task.cancel()

    asyncio.run(scenario())

    # Le front reçoit des messages qu'il sait afficher (actions.js, chat.js)
    assert sent[0][0] == "h"
    assert sent[0][1] == {"type": "action_request", "kind": "vote", "candidates": ["imp", "h"]}
    assert sent[1][1] == {"type": "chat", "channel_id": "public", "sender": "imp", "content": "Bonjour"}