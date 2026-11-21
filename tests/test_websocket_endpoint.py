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


@pytest.fixture(autouse=True)
def no_real_game(monkeypatch, clean_server):
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


# --- Historiques des onglets Nuits et Votes -----------------------------------

def test_historiques_nuits_et_votes_gardes_et_renvoyes_a_la_reconnexion():
    from types import SimpleNamespace
    port = QueueHumanPort()
    port.state = SimpleNamespace(turn=2, player=lambda pid: SimpleNamespace(name={"p1": "marIA"}[pid]))
    ws.ports["h"] = port

    async def fake_send(player_id, message):
        pass

    async def scenario():
        await ws._send_request("h", port, "night_info", {"turn": 2, "info": "L'un des deux est le Démon.", "allies": None})
        await ws._send_request("h", port, "night_deaths", {"deaths": ["p1"]})
        await ws.send_vote_result("h", 2, "marIA", [{"voter": "h", "target": "marIA"}, {"voter": "marIA", "target": None}])

    original = ws.manager.send_to_player
    ws.manager.send_to_player = fake_send
    try:
        asyncio.run(scenario())
    finally:
        ws.manager.send_to_player = original

    assert ws.night_log["h"] == [
        {"turn": 2, "type": "role_info", "info": "L'un des deux est le Démon."},
        {"turn": 2, "type": "result", "info": "marIA est mort·e cette nuit."},
    ]
    assert ws.vote_log["h"] == [
        {"turn": 2, "voter": "h", "target": "marIA", "executed": "marIA"},
        {"turn": 2, "voter": "marIA", "target": None, "executed": "marIA"},
    ]

    # Reconnexion : un seul message avec les deux historiques
    port.state = None  # l'état de la partie n'est pas l'objet de ce test
    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        history = json.loads(conn.receive_text())
    assert history == {"type": "history", "nights": ws.night_log["h"], "votes": ws.vote_log["h"]}


def test_nuit_sans_mort_dans_l_historique():
    assert ws.night_death_text(None) == "Personne n'est mort cette nuit."
    assert ws.night_death_text("marIA") == "marIA est mort·e cette nuit."


def test_resultat_du_tour_et_fin_de_partie_relayes_depuis_la_file():
    """game_runner pose vote_result et game_over dans la file : ils sont relayés comme les autres."""
    sent = []

    async def fake_send(player_id, message):
        sent.append(message)

    async def scenario():
        port = QueueHumanPort()
        await ws._send_request("h", port, "vote_result", {"turn": 3, "executed": None, "votes": []})
        await ws._send_request("h", port, "game_over", {"winner": "Villageois", "details": "Fin."})

    original = ws.manager.send_to_player
    ws.manager.send_to_player = fake_send
    try:
        asyncio.run(scenario())
    finally:
        ws.manager.send_to_player = original

    assert sent == [
        {"type": "vote_result", "turn": 3, "executed": None, "votes": []},
        {"type": "game_over", "winner": "Villageois", "details": "Fin."},
    ]
    assert ws.vote_log["h"] == []  # aucun bulletin à retenir ce tour-là


# --- Aucun choix de salon privé à temps : un agent propose un entretien ------------

def test_delai_de_discussion_ecoule_repond_none_au_moteur():
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "private_partners"

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.send_text(json.dumps({"action": "discussion_timeout", "payload": {}}))
        conn.send_text(json.dumps({"action": "discussion_timeout", "payload": {}}))  # plus rien n'est attendu
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "error"
    assert port.answers.get_nowait() is None
    assert port.answers.empty()


def test_proposition_d_un_agent_envoyee_au_front(monkeypatch):
    sent = []

    async def fake_send(player_id, message):
        sent.append(message)

    monkeypatch.setattr(ws.manager, "send_to_player", fake_send)

    async def scenario():
        port = QueueHumanPort()
        task = asyncio.create_task(ws._forward_requests("h", port))
        await port.requests.put({"kind": "agent_invitation", "agent": "imp"})
        await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(scenario())
    assert ws.pending["h"] == "agent_invitation"
    assert sent == [{"type": "agent_whisper_request", "agent_id": "imp", "agent_name": "imp"}]


def _invited_by(agent_id: str) -> QueueHumanPort:
    port = QueueHumanPort()
    ws.ports["h"] = port
    ws.pending["h"] = "agent_invitation"
    ws.current_request["h"] = ("agent_invitation", {"kind": "agent_invitation", "agent": agent_id})
    return port


def test_accepter_l_entretien_ouvre_le_salon():
    port = _invited_by("imp")

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.receive_text()  # proposition renvoyée à la connexion
        conn.send_text(json.dumps({"action": "respond_whisper_invitation",
                                   "payload": {"target_agent_id": "imp", "accepted": True}}))
        announce = json.loads(conn.receive_text())
        opened = json.loads(conn.receive_text())

    assert announce["sender"] == "Grimoire"
    assert opened["type"] == "private_channel_opened"
    assert opened["channel_id"] == "whisper_h_imp"
    assert ws.whispers["h"] == "whisper_h_imp"
    assert port.answers.get_nowait() is True


def test_refuser_l_entretien_passe_au_vote():
    port = _invited_by("imp")

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.receive_text()  # proposition renvoyée à la connexion
        conn.send_text(json.dumps({"action": "respond_whisper_invitation",
                                   "payload": {"target_agent_id": "imp", "accepted": False}}))
        reply = json.loads(conn.receive_text())

    assert reply["type"] == "announcement"
    assert "h" not in ws.whispers
    assert port.answers.get_nowait() is False


def test_reponse_a_un_autre_agent_ou_sans_proposition_refusee():
    port = _invited_by("imp")

    with make_client().websocket_connect("/ws/h") as conn:
        conn.receive_text()  # accusé "connected"
        conn.receive_text()  # proposition renvoyée à la connexion
        conn.send_text(json.dumps({"action": "respond_whisper_invitation",
                                   "payload": {"target_agent_id": "moine", "accepted": True}}))
        wrong_agent = json.loads(conn.receive_text())
        ws.pending["h"] = "vote"
        conn.send_text(json.dumps({"action": "respond_whisper_invitation",
                                   "payload": {"target_agent_id": "imp", "accepted": True}}))
        no_invitation = json.loads(conn.receive_text())

    assert wrong_agent["type"] == "error"
    assert no_invitation["type"] == "error"
    assert port.answers.empty()


def test_entretien_entre_deux_agents_annonce_sur_la_place_publique(monkeypatch):
    broadcast = []

    async def fake_broadcast(message):
        broadcast.append(message)

    monkeypatch.setattr(ws.manager, "broadcast", fake_broadcast)

    async def scenario():
        port = QueueHumanPort()
        task = asyncio.create_task(ws._forward_requests("h", port))
        await port.requests.put({"kind": "agent_meeting", "agents": ["imp", "moine"]})
        await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(scenario())
    message = {"type": "chat", "channel_id": "public", "sender": "Grimoire",
               "content": "💬 imp et moine se sont entretenus en privé."}
    assert broadcast == [message]
    assert ws.chat_log["h"] == [message]  # renvoyé après une reconnexion
    assert "h" not in ws.pending  # simple annonce : aucune réponse attendue
