"""Endpoint WebSocket et relais vers le front : réponses au moteur, salons, reprise après coupure,
étapes facultatives, historiques, proposition d'entretien d'un agent."""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models import GameState, Phase, Player
from backend.rules import get_role
from backend.server import game_runner, protocol
from backend.server import websocket_endpoint as ws
from backend.server.schemas import NightHistoryEntry, VoteHistoryEntry
from server_helpers import waiting_session

NAMES = {"h": "Alex", "imp": "Imp", "p1": "marIA", "moine": "Veilleur"}
ROLES = {"h": "medium", "imp": "reaper", "p1": "apothecary", "moine": "watchman"}


def make_state(dead=()) -> GameState:
    return GameState(turn=2, phase=Phase.DISCUSSION, players=tuple(
        Player(id=pid, name=NAMES[pid], role=get_role(ROLES[pid]), alive=pid not in dead) for pid in NAMES))


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(ws.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def no_real_game(monkeypatch, clean_server):
    """Se connecter ne doit pas lancer une vraie partie : la session est préparée par chaque test."""
    monkeypatch.setattr(game_runner, "ensure_started", lambda player_id: None)


def waiting(kind=None, **request):
    """Session de « h » dont le moteur attend `kind`, avec un état de partie réel."""
    return waiting_session("h", kind, make_state(), **request)


def connect(conn) -> list[dict]:
    """Messages reçus à la connexion (accusé, rôle, état, chat, demande renvoyée…).
    On s'arrête sur la réponse à un JSON invalide : tout ce qui précède a été envoyé à la connexion."""
    conn.send_text("pas du json")
    received = []
    while True:
        message = json.loads(conn.receive_text())
        if message == {"type": "error", "data": "Format JSON invalide."}:
            return received
        received.append(message)


def act(conn, action, **payload) -> dict:
    conn.send_text(json.dumps({"action": action, "payload": payload}))
    return json.loads(conn.receive_text())


def relay(session, *requests) -> list[dict]:
    """Le relais traduit des demandes du moteur (comme forward_requests, sans la file).
    Renvoie les messages envoyés au joueur (et diffusés), sans vraie connexion."""
    sent = []

    async def fake_send(*args):
        sent.append(args[-1])

    async def scenario():
        for request in requests:
            await protocol.send_request(session, {"state": session.state, **request})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(protocol.manager, "send_to_player", fake_send)
        patch.setattr(protocol.manager, "broadcast", fake_send)
        asyncio.run(scenario())
    return sent


# --- Réponses au moteur (identifiants des joueurs) ---------------------------------

def test_empty_vote_arrives_as_none():
    session = waiting("vote", targets=["h", "imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="")
    assert reply == {"type": "announcement", "text": "Votre vote pour Personne a bien été pris en compte."}
    assert session.port.answers.get_nowait() is None


def test_vote_with_target_arrives_unchanged():
    session = waiting("vote", targets=["h", "imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="imp")
    assert reply["text"] == "Votre vote pour Imp a bien été pris en compte."
    assert session.port.answers.get_nowait() == "imp"


def test_target_not_offered_refused():
    session = waiting("vote", targets=["h", "imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="Imp")  # un nom n'est pas un identifiant
    assert reply["type"] == "error"
    assert session.port.answers.empty()


def test_vote_outside_its_phase_refused():
    session = waiting("night_choice", targets=["imp"], count=1)
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="imp")
    assert reply["type"] == "error"
    assert session.port.answers.empty()


def test_night_action_arrives_as_tuple():
    session = waiting("night_choice", targets=["imp", "p1"], count=1)
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_night_action", targets=["imp"])
    assert reply["type"] == "night_action_ack"
    assert session.port.answers.get_nowait() == ("imp",)


def test_unknown_field_refused():
    session = waiting("vote", targets=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", targt_id="imp")
    assert reply["type"] == "error"
    assert session.port.answers.empty()


def test_action_without_game_refused():
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="imp")
    assert reply == {"type": "error", "data": "Aucune partie en cours."}


def test_whisper_opens_the_channel_and_answers_the_engine():
    session = waiting("private_partners", choices=["imp", "p1", "moine"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        announce = act(conn, "request_whisper", targets=["imp"])
        opened = json.loads(conn.receive_text())

    assert announce == {"type": "chat", "channel_id": "public", "sender": "Codex",
                        "content": "💬 Alex est entré en discussion privée avec Imp."}
    assert opened == {"type": "private_channel_opened", "channel_id": "whisper_h_imp", "members": ["h", "imp"],
                      "text": "Salon privé ouvert avec Imp", "focus": True}
    assert session.whisper == "whisper_h_imp"
    assert session.port.answers.get_nowait() == ["imp"]


# --- Reprise après rechargement ------------------------------------------------------

def test_reconnection_reopens_the_channel_and_resends_the_chat():
    session = waiting("private_partners", choices=["imp", "p1"])
    client = make_client()

    # Première connexion : le joueur ouvre un salon puis y écrit
    with client.websocket_connect("/ws/h") as conn:
        connect(conn)
        act(conn, "request_whisper", targets=["imp"])
        conn.receive_text()  # salon ouvert
        session.pending = {"kind": "private_message", "state": session.state}
        act(conn, "send_chat", channel_id="whisper_h_imp", content="Psst")

    # Rechargement : rôle, état, salon et messages reviennent, sans placer le joueur dans le salon
    with client.websocket_connect("/ws/h") as conn:
        messages = connect(conn)

    assert [m["type"] for m in messages] == [
        "connected", "role_assigned", "game_state", "private_channel_opened", "chat", "chat"]
    assert messages[3] == {"type": "private_channel_opened", "channel_id": "whisper_h_imp",
                           "members": ["h", "imp"], "text": "", "focus": False}
    assert messages[4]["sender"] == "Codex"
    assert messages[5] == {"type": "chat", "channel_id": "whisper_h_imp", "sender": "h", "content": "Psst"}


def test_revealed_allies_resent_with_the_role():
    session = waiting()
    # La révélation de la première nuit est retenue…
    relay(session, {"kind": "night_info", "turn": 1, "info": "Ton allié est marIA.",
                    "allies": [{"id": "p1", "role": "Apothicaire"}]})

    # …et renvoyée avec le rôle à la reconnexion
    with make_client().websocket_connect("/ws/h") as conn:
        role = next(m for m in connect(conn) if m["type"] == "role_assigned")
    assert role["allies"] == [{"id": "p1", "role": "Apothicaire"}]


# --- Étapes facultatives -------------------------------------------------------------

@pytest.mark.parametrize("kind, nothing", [("public_message", None), ("private_message", None)])
def test_skip_a_message(kind, nothing):
    session = waiting(kind)
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        conn.send_text(json.dumps({"action": "skip_turn", "payload": {"kind": kind}}))
        connect(conn)  # synchronisation : l'action précédente est traitée
    assert session.port.answers.get_nowait() is nothing
    assert session.pending is None


def test_skip_to_vote_without_private_channel():
    session = waiting("private_partners", choices=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "skip_turn", kind="private_partners")
    assert reply["type"] == "announcement"
    assert session.port.answers.get_nowait() == []  # « personne » pour le moteur


def test_skipping_an_unexpected_step_refused():
    session = waiting("vote", targets=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "skip_turn", kind="public_message")
    assert reply["type"] == "error"
    assert session.port.answers.empty()
    assert session.waits_for("vote")


def test_vote_cannot_be_skipped():
    waiting("vote", targets=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        assert act(conn, "skip_turn", kind="vote")["data"].startswith("Action non valide")


def test_expected_input_announced_to_the_front():
    session = waiting()
    session.whisper, session.whisper_left = "whisper_h_imp", 2
    sent = relay(session, {"kind": "public_message"}, {"kind": "private_message"})

    assert sent[0] == {"type": "input_request", "kind": "public_message", "channel_id": "public",
                       "text": "C'est à vous de parler sur la place publique.", "left": None}
    assert sent[1] == {"type": "input_request", "kind": "private_message", "channel_id": "whisper_h_imp",
                       "left": 2, "text": "Il vous reste 2 message(s) privé(s) avec vos interlocuteurs."}


# --- Historiques des onglets Nuits et Votes -------------------------------------------

def test_night_and_vote_histories_kept_and_resent_on_reconnection():
    session = waiting()
    sent = relay(session,
                 {"kind": "night_info", "turn": 2, "info": "L'un des deux est le Démon.", "allies": None},
                 {"kind": "night_deaths", "deaths": ["p1"]},
                 {"kind": "vote_result", "turn": 2, "executed": "p1",
                  "votes": [{"voter": "h", "target": "p1", "ghost": False},
                            {"voter": "p1", "target": None, "ghost": False}]})

    # Le front reçoit l'identifiant du mort : c'est lui qui écrit le texte
    assert {"type": "night_result", "turn": 2, "dead_player": "p1"} in sent
    assert session.night_log == [
        NightHistoryEntry(turn=2, type="role_info", info="L'un des deux est le Démon."),
        NightHistoryEntry(turn=2, type="result", dead_player="p1"),
    ]
    assert session.vote_log == [
        VoteHistoryEntry(turn=2, voter="h", target="p1", executed="p1"),
        VoteHistoryEntry(turn=2, voter="p1", target=None, executed="p1"),
    ]

    # Reconnexion : un seul message avec les deux historiques
    with make_client().websocket_connect("/ws/h") as conn:
        history = next(m for m in connect(conn) if m["type"] == "history")
    assert history["nights"] == [
        {"turn": 2, "type": "role_info", "info": "L'un des deux est le Démon.", "dead_player": None},
        {"turn": 2, "type": "result", "info": None, "dead_player": "p1"},
    ]
    assert history["votes"][0] == {"turn": 2, "voter": "h", "target": "p1", "executed": "p1", "unavailable": False}


def test_night_without_death():
    session = waiting()
    sent = relay(session, {"kind": "night_deaths", "deaths": []})
    assert sent == [{"type": "night_result", "turn": 2, "dead_player": None}]


def test_turn_result_and_game_over_relayed_from_the_queue():
    """game_runner pose vote_result et game_over dans la file : ils sont relayés comme les autres."""
    session = waiting()
    sent = relay(session, {"kind": "vote_result", "turn": 3, "executed": None, "votes": []},
                 {"kind": "game_over", "winner": "good", "details": "Fin."})

    assert sent == [
        {"type": "vote_result", "turn": 3, "executed": None, "votes": []},
        {"type": "game_over", "winner": "good", "details": "Fin."},
    ]
    assert session.vote_log == []  # aucun bulletin à retenir ce tour-là


# --- Aucun choix de salon privé à temps : un agent propose un entretien ------------------

def test_discussion_timeout_answers_none_to_the_engine():
    session = waiting("private_partners", choices=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        conn.send_text(json.dumps({"action": "discussion_timeout", "payload": {}}))
        reply = act(conn, "discussion_timeout")  # plus rien n'est attendu
    assert reply["type"] == "error"
    assert session.port.answers.get_nowait() is None
    assert session.port.answers.empty()


def test_agent_invitation_sent_to_the_front():
    session = waiting()
    sent = relay(session, {"kind": "agent_invitation", "agent": "imp"})
    assert sent == [{"type": "agent_whisper_request", "agent_id": "imp"}]


def test_accepting_the_invitation_opens_the_channel():
    session = waiting("agent_invitation", agent="imp")
    with make_client().websocket_connect("/ws/h") as conn:
        assert connect(conn)[-1] == {"type": "agent_whisper_request", "agent_id": "imp"}  # renvoyée
        announce = act(conn, "respond_whisper_invitation", target_agent_id="imp", accepted=True)
        opened = json.loads(conn.receive_text())

    assert announce["sender"] == "Codex"
    assert opened["type"] == "private_channel_opened" and opened["channel_id"] == "whisper_h_imp"
    assert session.whisper == "whisper_h_imp"
    assert session.port.answers.get_nowait() is True


def test_refusing_the_invitation_goes_to_the_vote():
    session = waiting("agent_invitation", agent="imp")
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "respond_whisper_invitation", target_agent_id="imp", accepted=False)
    assert reply["type"] == "announcement"
    assert session.whisper is None
    assert session.port.answers.get_nowait() is False


def test_answer_for_another_agent_or_without_invitation_refused():
    session = waiting("agent_invitation", agent="imp")
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        wrong_agent = act(conn, "respond_whisper_invitation", target_agent_id="moine", accepted=True)
        session.pending = {"kind": "vote", "state": session.state, "targets": ["imp"]}
        no_invitation = act(conn, "respond_whisper_invitation", target_agent_id="imp", accepted=True)
    assert wrong_agent["type"] == "error"
    assert no_invitation["type"] == "error"
    assert session.port.answers.empty()


def test_meeting_between_two_agents_announced_publicly():
    session = waiting()
    sent = relay(session, {"kind": "agent_meeting", "agents": ["imp", "moine"]})

    message = {"type": "chat", "channel_id": "public", "sender": "Codex",
               "content": "💬 Imp et Veilleur se sont entretenus en privé."}
    assert sent == [message]
    assert [m.model_dump() for m in session.chat_log] == [message]  # renvoyé après une reconnexion


# --- IA indisponible : ce que le joueur voit selon le moment ---------------------------

def test_unavailable_agent_in_public_discussion_announced_by_the_codex():
    session = waiting()
    sent = relay(session, {"kind": "agent_unavailable", "agent": "imp", "step": "public"})
    assert sent == [{"type": "chat", "channel_id": "public", "sender": "Codex",
                     "content": "🕯️ Imp ne dit rien : son IA n'a pas répondu."}]


def test_unavailable_agent_in_private_channel_announced_in_the_channel():
    session = waiting()
    session.whisper = "whisper_h_imp"
    sent = relay(session, {"kind": "agent_unavailable", "agent": "imp", "step": "private"})
    assert sent[0]["channel_id"] == "whisper_h_imp"
    assert sent[0]["content"] == "🕯️ Imp ne répond pas : son IA n'a pas répondu."


@pytest.mark.parametrize("step", ["night", "vote"])
def test_unavailable_agent_at_night_or_vote_shows_nothing_but_is_kept_for_admin(step):
    """Nuit : l'annoncer révélerait un pouvoir. Vote : la mention est sur le bulletin."""
    session = waiting()
    assert relay(session, {"kind": "agent_unavailable", "agent": "imp", "step": step}) == []
    assert session.agent_failures == [{"turn": 2, "phase": "discussion", "agent": "imp", "step": step}]


def test_banner_once_when_failures_pile_up():
    session = waiting()
    failure = {"kind": "agent_unavailable", "agent": "imp", "step": "night"}
    sent = relay(session, failure, failure, failure, failure)
    assert sent == [{"type": "announcement",
                     "text": "Les IA rencontrent des difficultés : la partie continue avec des réponses de secours."}]
