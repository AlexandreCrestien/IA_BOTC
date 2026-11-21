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
from backend.server import websockets as ws
from backend.server.schemas import NightHistoryEntry, VoteHistoryEntry
from server_helpers import waiting_session

NAMES = {"h": "Alex", "imp": "Imp", "p1": "marIA", "moine": "Moine"}
ROLES = {"h": "psychic", "imp": "imp", "p1": "poisoner", "moine": "monk"}


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

def test_vote_vide_arrive_comme_none():
    session = waiting("vote", targets=["h", "imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="")
    assert reply == {"type": "announcement", "text": "Votre vote pour Personne a bien été pris en compte."}
    assert session.port.answers.get_nowait() is None


def test_vote_avec_cible_arrive_tel_quel():
    session = waiting("vote", targets=["h", "imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="imp")
    assert reply["text"] == "Votre vote pour Imp a bien été pris en compte."
    assert session.port.answers.get_nowait() == "imp"


def test_cible_non_proposee_refusee():
    session = waiting("vote", targets=["h", "imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="Imp")  # un nom n'est pas un identifiant
    assert reply["type"] == "error"
    assert session.port.answers.empty()


def test_vote_hors_phase_est_refuse():
    session = waiting("night_choice", targets=["imp"], count=1)
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="imp")
    assert reply["type"] == "error"
    assert session.port.answers.empty()


def test_action_de_nuit_arrive_en_tuple():
    session = waiting("night_choice", targets=["imp", "p1"], count=1)
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_night_action", targets=["imp"])
    assert reply["type"] == "night_action_ack"
    assert session.port.answers.get_nowait() == ("imp",)


def test_champ_inconnu_est_refuse():
    session = waiting("vote", targets=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", targt_id="imp")
    assert reply["type"] == "error"
    assert session.port.answers.empty()


def test_action_sans_partie_refusee():
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "submit_vote", target_id="imp")
    assert reply == {"type": "error", "data": "Aucune partie en cours."}


def test_whisper_ouvre_le_salon_et_repond_au_moteur():
    session = waiting("private_partners", choices=["imp", "p1", "moine"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        announce = act(conn, "request_whisper", targets=["imp"])
        opened = json.loads(conn.receive_text())

    assert announce == {"type": "chat", "channel_id": "public", "sender": "Grimoire",
                        "content": "💬 Alex est entré en discussion privée avec Imp."}
    assert opened == {"type": "private_channel_opened", "channel_id": "whisper_h_imp", "members": ["h", "imp"],
                      "text": "Salon privé ouvert avec Imp", "focus": True}
    assert session.whisper == "whisper_h_imp"
    assert session.port.answers.get_nowait() == ["imp"]


# --- Reprise après rechargement ------------------------------------------------------

def test_reconnexion_rouvre_le_salon_et_renvoie_l_historique_du_chat():
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
    assert messages[4]["sender"] == "Grimoire"
    assert messages[5] == {"type": "chat", "channel_id": "whisper_h_imp", "sender": "h", "content": "Psst"}


def test_les_allies_reveles_sont_renvoyes_avec_le_role():
    session = waiting()
    # La révélation de la première nuit est retenue…
    relay(session, {"kind": "night_info", "turn": 1, "info": "Ton allié est marIA.",
                    "allies": [{"id": "p1", "role": "Empoisonneur"}]})

    # …et renvoyée avec le rôle à la reconnexion
    with make_client().websocket_connect("/ws/h") as conn:
        role = next(m for m in connect(conn) if m["type"] == "role_assigned")
    assert role["allies"] == [{"id": "p1", "role": "Empoisonneur"}]


# --- Étapes facultatives -------------------------------------------------------------

@pytest.mark.parametrize("kind, nothing", [("public_message", None), ("private_message", None)])
def test_passer_un_message(kind, nothing):
    session = waiting(kind)
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        conn.send_text(json.dumps({"action": "skip_turn", "payload": {"kind": kind}}))
        connect(conn)  # synchronisation : l'action précédente est traitée
    assert session.port.answers.get_nowait() is nothing
    assert session.pending is None


def test_passer_au_vote_sans_salon_prive():
    session = waiting("private_partners", choices=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "skip_turn", kind="private_partners")
    assert reply["type"] == "announcement"
    assert session.port.answers.get_nowait() == []  # « personne » pour le moteur


def test_passer_une_etape_qui_n_est_pas_attendue_est_refuse():
    session = waiting("vote", targets=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "skip_turn", kind="public_message")
    assert reply["type"] == "error"
    assert session.port.answers.empty()
    assert session.waits_for("vote")


def test_le_vote_ne_peut_pas_etre_passe_par_skip_turn():
    waiting("vote", targets=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        assert act(conn, "skip_turn", kind="vote")["data"].startswith("Action non valide")


def test_saisie_attendue_annoncee_au_front():
    session = waiting()
    session.whisper, session.whisper_left = "whisper_h_imp", 2
    sent = relay(session, {"kind": "public_message"}, {"kind": "private_message"})

    assert sent[0] == {"type": "input_request", "kind": "public_message", "channel_id": "public",
                       "text": "C'est à vous de parler sur la place publique.", "left": None}
    assert sent[1] == {"type": "input_request", "kind": "private_message", "channel_id": "whisper_h_imp",
                       "left": 2, "text": "Il vous reste 2 message(s) privé(s) avec vos interlocuteurs."}


# --- Historiques des onglets Nuits et Votes -------------------------------------------

def test_historiques_nuits_et_votes_gardes_et_renvoyes_a_la_reconnexion():
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
    assert history["votes"][0] == {"turn": 2, "voter": "h", "target": "p1", "executed": "p1"}


def test_nuit_sans_mort():
    session = waiting()
    sent = relay(session, {"kind": "night_deaths", "deaths": []})
    assert sent == [{"type": "night_result", "turn": 2, "dead_player": None}]


def test_resultat_du_tour_et_fin_de_partie_relayes_depuis_la_file():
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

def test_delai_de_discussion_ecoule_repond_none_au_moteur():
    session = waiting("private_partners", choices=["imp"])
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        conn.send_text(json.dumps({"action": "discussion_timeout", "payload": {}}))
        reply = act(conn, "discussion_timeout")  # plus rien n'est attendu
    assert reply["type"] == "error"
    assert session.port.answers.get_nowait() is None
    assert session.port.answers.empty()


def test_proposition_d_un_agent_envoyee_au_front():
    session = waiting()
    sent = relay(session, {"kind": "agent_invitation", "agent": "imp"})
    assert sent == [{"type": "agent_whisper_request", "agent_id": "imp"}]


def test_accepter_l_entretien_ouvre_le_salon():
    session = waiting("agent_invitation", agent="imp")
    with make_client().websocket_connect("/ws/h") as conn:
        assert connect(conn)[-1] == {"type": "agent_whisper_request", "agent_id": "imp"}  # renvoyée
        announce = act(conn, "respond_whisper_invitation", target_agent_id="imp", accepted=True)
        opened = json.loads(conn.receive_text())

    assert announce["sender"] == "Grimoire"
    assert opened["type"] == "private_channel_opened" and opened["channel_id"] == "whisper_h_imp"
    assert session.whisper == "whisper_h_imp"
    assert session.port.answers.get_nowait() is True


def test_refuser_l_entretien_passe_au_vote():
    session = waiting("agent_invitation", agent="imp")
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        reply = act(conn, "respond_whisper_invitation", target_agent_id="imp", accepted=False)
    assert reply["type"] == "announcement"
    assert session.whisper is None
    assert session.port.answers.get_nowait() is False


def test_reponse_a_un_autre_agent_ou_sans_proposition_refusee():
    session = waiting("agent_invitation", agent="imp")
    with make_client().websocket_connect("/ws/h") as conn:
        connect(conn)
        wrong_agent = act(conn, "respond_whisper_invitation", target_agent_id="moine", accepted=True)
        session.pending = {"kind": "vote", "state": session.state, "targets": ["imp"]}
        no_invitation = act(conn, "respond_whisper_invitation", target_agent_id="imp", accepted=True)
    assert wrong_agent["type"] == "error"
    assert no_invitation["type"] == "error"
    assert session.port.answers.empty()


def test_entretien_entre_deux_agents_annonce_sur_la_place_publique():
    session = waiting()
    sent = relay(session, {"kind": "agent_meeting", "agents": ["imp", "moine"]})

    message = {"type": "chat", "channel_id": "public", "sender": "Grimoire",
               "content": "💬 Imp et Moine se sont entretenus en privé."}
    assert sent == [message]
    assert [m.model_dump() for m in session.chat_log] == [message]  # renvoyé après une reconnexion
