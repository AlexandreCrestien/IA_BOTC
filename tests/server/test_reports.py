"""Signalements des messages des agents IA : enregistrement (comptes seulement, pseudo retiré, modèle gardé),
limites, suivi par l'admin, suppression du compte, durée de conservation, export des données."""
import asyncio
import random
from datetime import timedelta

import pytest

from backend.accounts import service
from backend.ai.llm_client import LLMText
from backend.db import AgentReport, GameDetail, get_session
from backend.db.models import utcnow
from backend.engine.setup import setup_game
from backend.server import game_records, protocol, reports
from backend.server.reports import MAX_REPORTS_PER_GAME, save_report, without_pseudo
from backend.server.session import GameSession, set_current_session

NAMES = {"Vesper": "Vesper", "p1": "marIA", "p2": "tobIAs", "p3": "mAIsie", "p4": "adrIAn", "p5": "dIAne"}
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]
MODEL = "groq/openai/gpt-oss-20b"


def account(pseudo="Vesper") -> int:
    with get_session() as db:
        user = service.register(db, pseudo, "mot-de-passe", f"{pseudo.lower()}@exemple.fr")
        user.email_verified_at = utcnow()
        db.commit()
        return user.id


def game(user_id=None) -> GameSession:
    """Partie réelle mise en place (moteur, agents), du compte user_id (None : invité)."""
    state, agents, memory = setup_game(NAMES, "Vesper", PERSONALITIES, random.Random(0))
    session = GameSession(human_id="Vesper", user_id=user_id, state=state, memory=memory, agents=agents)
    set_current_session(session)
    game_records.open_record(session)
    return session


def agent_says(session, text="Vesper ment, j'en suis sûr.", agent="p1", channel=protocol.PUBLIC_CHANNEL) -> str:
    """Message d'un agent IA envoyé au joueur ; renvoie son identifiant."""
    asyncio.run(protocol.send_agent_message(session, channel, agent, LLMText(text, MODEL)))
    return list(session.ai_messages)[-1]


# --- Messages des agents -------------------------------------------------------------------

def test_agent_messages_get_an_id_but_never_reveal_their_model(db, sent):
    session = game()
    first, second = agent_says(session), agent_says(session, agent="p2")
    assert (first, second) == ("m1", "m2")
    assert sent[-1] == {"type": "chat", "channel_id": "public", "sender": "p2", "content": "Vesper ment, j'en suis sûr.",
                        "message_id": "m2", "reported": False}
    assert MODEL not in str(sent)
    assert session.ai_messages["m1"]["model"] == MODEL


def test_human_and_codex_messages_cannot_be_reported(db, sent):
    session = game()
    asyncio.run(protocol.send_chat(session, protocol.PUBLIC_CHANNEL, "Vesper", "Bonsoir"))
    assert sent[-1]["message_id"] is None and session.ai_messages == {}


def test_pseudo_is_replaced_as_a_whole_word_whatever_the_case():
    text = "VESPER ment. Vesperine n'a rien dit, mais vesper, si."
    assert without_pseudo(text, "Vesper") == "[joueur] ment. Vesperine n'a rien dit, mais [joueur], si."
    assert without_pseudo("Écoute O'Neil-2 !", "O'Neil-2") == "Écoute [joueur] !"


# --- Enregistrement --------------------------------------------------------------------------

def test_report_keeps_agent_model_and_message_without_the_pseudo(db, sent):
    user_id = account()
    session = game(user_id)
    message_id = agent_says(session, agent="p1")

    assert save_report(session, message_id, "knowledge", "  Il connaît mon rôle.  ") is None

    report = db.query(AgentReport).one()
    agent = session.agents["p1"]
    assert (report.user_id, report.game_id) == (user_id, session.record_id)
    assert (report.agent, report.personality, report.role) == ("marIA", agent.personality_key, agent.role.name_EN)
    assert (report.model, report.channel, report.moment) == (MODEL, "public", "Nuit 1")
    assert report.message == "[joueur] ment, j'en suis sûr."
    assert (report.category, report.comment, report.handled_at) == ("knowledge", "Il connaît mon rôle.", None)
    assert session.ai_messages[message_id]["message"].reported  # renvoyé « signalé » à la reconnexion


def test_private_message_report_records_the_channel(db, sent):
    session = game(account())
    message_id = agent_says(session, channel="whisper_Vesper_p1")
    assert save_report(session, message_id, "character", None) is None
    assert db.query(AgentReport).one().channel == "private"


def test_guests_cannot_report(db, sent):
    session = game()
    assert save_report(session, agent_says(session), "rules", None) == reports.GUESTS_REFUSED
    assert db.query(AgentReport).count() == 0


@pytest.mark.parametrize("category, comment, error", [
    ("other", None, reports.COMMENT_REQUIRED),
    ("other", "   ", reports.COMMENT_REQUIRED),
    ("rules", "x" * 201, reports.COMMENT_TOO_LONG.format(max=200)),
    ("other", "x" * 501, reports.COMMENT_TOO_LONG.format(max=500)),
])
def test_comment_rules(db, sent, category, comment, error):
    session = game(account())
    assert save_report(session, agent_says(session), category, comment) == error


def test_long_comment_allowed_for_other(db, sent):
    session = game(account())
    assert save_report(session, agent_says(session), "other", "x" * 500) is None


def test_unknown_or_already_reported_message_is_refused(db, sent):
    session = game(account())
    message_id = agent_says(session)
    assert save_report(session, "m99", "rules", None) == reports.UNKNOWN_MESSAGE
    assert save_report(session, message_id, "rules", None) is None
    assert save_report(session, message_id, "rules", None) == reports.ALREADY_REPORTED
    assert db.query(AgentReport).count() == 1


def test_reports_are_limited_per_game(db, sent):
    session = game(account())
    ids = [agent_says(session) for _ in range(MAX_REPORTS_PER_GAME + 1)]
    for message_id in ids[:-1]:
        assert save_report(session, message_id, "rules", None) is None
    assert save_report(session, ids[-1], "rules", None) == reports.TOO_MANY_REPORTS


# --- Action WebSocket --------------------------------------------------------------------------

def test_report_action_answers_with_its_result(db, sent):
    from backend.server.schemas import ReportMessagePayload
    from backend.server.websocket_endpoint import on_report_message
    session = game(account())
    message_id = agent_says(session)

    asyncio.run(on_report_message(session, ReportMessagePayload(message_id=message_id, category="rules")))
    assert sent[-1] == {"type": "report_result", "message_id": message_id, "error": None}
    asyncio.run(on_report_message(session, ReportMessagePayload(message_id=message_id, category="rules")))
    assert sent[-1]["error"] == reports.ALREADY_REPORTED
    assert session.pending is None  # une erreur de signalement ne touche pas la demande en cours


# --- RGPD : suppression du compte, conservation, export ------------------------------------------

def test_account_deletion_keeps_the_report_without_account_nor_comment(db, sent):
    user_id = account()
    session = game(user_id)
    save_report(session, agent_says(session), "other", "Je m'appelle Vesper Dupont.")

    service.delete_account(db, service.find_by_pseudo(db, "Vesper"))

    db.expire_all()
    report = db.query(AgentReport).one()
    assert (report.user_id, report.comment) == (None, None)
    assert (report.agent, report.model, report.category) == ("marIA", MODEL, "other")


def test_handled_reports_are_deleted_six_months_after_handling(db, sent):
    session = game(account())
    for _ in range(3):
        save_report(session, agent_says(session), "rules", None)
    old, recent, pending = db.query(AgentReport).order_by(AgentReport.id).all()
    now = utcnow()
    old.handled_at = now - timedelta(days=184)
    recent.handled_at = now - timedelta(days=100)
    pending.created_at = now - timedelta(days=400)  # en attente : gardé, quel que soit son âge
    db.commit()

    service.delete_expired_records(db, now=now)

    db.expire_all()
    assert [r.id for r in db.query(AgentReport).order_by(AgentReport.id)] == [recent.id, pending.id]


def test_export_contains_the_player_reports(db, sent):
    from backend.stats.queries import export_account
    session = game(account())
    save_report(session, agent_says(session), "character", "Trop moderne.")
    exported = export_account(db, service.find_by_pseudo(db, "Vesper"))
    assert exported["reports"] == [{
        "date": exported["reports"][0]["date"], "agent": "marIA", "moment": "Nuit 1",
        "message": "[joueur] ment, j'en suis sûr.", "problem": "Sort de son personnage",
        "comment": "Trop moderne.", "handled": False,
    }]


# --- Panel admin -------------------------------------------------------------------------------

def admin(client):
    client.post("/api/auth/login", json={"login": "Gardien", "password": "mot-de-passe-admin"})
    return client


def test_admin_lists_reports_with_link_to_the_game(client, sent):
    session = game(account())
    save_report(session, agent_says(session), "knowledge", "Bizarre")

    listed = admin(client).get("/admin/reports").json()
    assert len(listed) == 1
    report = listed[0]
    assert report["agent"] == "marIA" and report["model"] == MODEL and report["reporter"] == "Vesper"
    assert report["category_label"] == "Révèle une information qu'il ne devrait pas connaître"
    assert report["handled"] is False
    assert report["game_link"] == "current"  # partie en cours : détail pas encore enregistré

    game_records.close_record(session, game_records.GameStatus.WON, turns=2)
    assert admin(client).get("/admin/reports").json()[0]["game_link"] == "detail"

    with get_session() as db:
        db.query(GameDetail).delete()
        db.commit()
    set_current_session(None)
    assert admin(client).get("/admin/reports").json()[0]["game_link"] is None


def test_admin_marks_a_report_as_handled_then_pending(client, sent):
    session = game(account())
    save_report(session, agent_says(session), "rules", None)
    report_id = admin(client).get("/admin/reports").json()[0]["id"]

    handled = client.put(f"/admin/reports/{report_id}/status", json={"handled": True}).json()
    assert handled["handled"] is True and handled["handled_at"]
    assert client.put(f"/admin/reports/{report_id}/status", json={"handled": False}).json()["handled_at"] is None
    assert client.put("/admin/reports/999/status", json={"handled": True}).status_code == 404


def test_report_routes_are_reserved_to_the_admin(client):
    assert client.get("/admin/reports").status_code == 401
    account("Joueur")
    client.post("/api/auth/login", json={"login": "Joueur", "password": "mot-de-passe"})
    assert client.get("/admin/reports").status_code == 403
