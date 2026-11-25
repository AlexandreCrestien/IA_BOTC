"""Évaluation des agents IA en fin de partie : enregistrement (comptes, parties terminées, une fois par partie),
modèle principal de l'agent, moyennes du panel admin, suppression du compte, durée de conservation, export."""
import asyncio
from datetime import timedelta

import pytest

from backend.accounts import service
from backend.ai.llm_client import LLMText
from backend.db import AgentRating, GameStatus
from backend.db.models import utcnow
from backend.server import game_records, protocol, ratings
from backend.server.ratings import main_model, save_ratings
from backend.server.schemas import AgentRatingIn, RateAgentsPayload
from test_reports import account, admin, game

FAST, OTHER = "groq/openai/gpt-oss-20b", "gemini/gemini-3.1-flash-lite"


def finished(user_id=None, status=GameStatus.WON):
    session = game(user_id)
    game_records.close_record(session, status, turns=3)
    return session


def says(session, agent, model):
    asyncio.run(protocol.send_agent_message(session, protocol.PUBLIC_CHANNEL, agent, LLMText("Bonsoir Vesper.", model)))


def notes(*items):
    return [AgentRatingIn(agent_id=agent, score=score, comment=comment) for agent, score, comment in items]


# --- Enregistrement --------------------------------------------------------------------------

def test_ratings_keep_agent_and_main_model(db, sent):
    session = finished(account())
    for model in (FAST, FAST, OTHER):
        says(session, "p1", model)
    says(session, "p2", OTHER)

    assert save_ratings(session, notes(("p1", 4, "  Très crédible, Vesper s'est fait avoir. "), ("p3", 2, None))) is None

    rows = db.query(AgentRating).order_by(AgentRating.id).all()
    agent = session.agents["p1"]
    assert [(r.agent, r.score, r.model) for r in rows] == [("marIA", 4, FAST), ("mAIsie", 2, None)]
    assert (rows[0].personality, rows[0].role) == (agent.personality_key, agent.role.name_EN)
    assert rows[0].game_id == session.record_id
    assert rows[0].comment == "Très crédible, [joueur] s'est fait avoir."  # pseudo retiré
    assert rows[1].comment is None
    assert session.rated


def test_main_model_is_the_most_frequent():
    from backend.server.session import GameSession
    session = GameSession(human_id="h")
    session.ai_messages = {"m1": {"agent": "p1", "model": OTHER}, "m2": {"agent": "p1", "model": FAST},
                           "m3": {"agent": "p1", "model": FAST}, "m4": {"agent": "p2", "model": OTHER}}
    assert main_model(session, "p1") == FAST
    assert main_model(session, "p5") is None


@pytest.mark.parametrize("status", [GameStatus.WON, GameStatus.LOST])
def test_won_or_lost_games_can_be_rated(db, sent, status):
    assert save_ratings(finished(account(), status), notes(("p1", 3, None))) is None


@pytest.mark.parametrize("status", [GameStatus.ABANDONED, GameStatus.INTERRUPTED])
def test_abandoned_or_interrupted_games_cannot_be_rated(db, sent, status):
    assert save_ratings(finished(account(), status), notes(("p1", 3, None))) == ratings.NOT_FINISHED


def test_game_in_progress_cannot_be_rated(db, sent):
    assert save_ratings(game(account()), notes(("p1", 3, None))) == ratings.NOT_FINISHED


def test_guests_cannot_rate(db, sent):
    assert save_ratings(finished(), notes(("p1", 3, None))) == ratings.GUESTS_REFUSED
    assert db.query(AgentRating).count() == 0


def test_only_once_per_game(db, sent):
    session = finished(account())
    assert save_ratings(session, notes(("p1", 3, None))) is None
    assert save_ratings(session, notes(("p2", 3, None))) == ratings.ALREADY_RATED
    assert db.query(AgentRating).count() == 1


def test_unknown_or_duplicate_agent_is_refused(db, sent):
    session = finished(account())
    assert save_ratings(session, notes(("Vesper", 3, None))) == ratings.UNKNOWN_AGENT  # le joueur lui-même
    assert save_ratings(session, notes(("p1", 3, None), ("p1", 5, None))) == ratings.DUPLICATE_AGENT
    assert db.query(AgentRating).count() == 0 and not session.rated


@pytest.mark.parametrize("payload", [
    {"ratings": []},
    {"ratings": [{"agent_id": "p1", "score": 0}]},
    {"ratings": [{"agent_id": "p1", "score": 6}]},
    {"ratings": [{"agent_id": "p1", "score": 3, "comment": "x" * 301}]},
])
def test_payload_rules(payload):
    with pytest.raises(ValueError):
        RateAgentsPayload.model_validate(payload)


def test_rate_action_answers_with_its_result(db, sent):
    from backend.server.websocket_endpoint import on_rate_agents
    session = finished(account())
    payload = RateAgentsPayload(ratings=[{"agent_id": "p1", "score": 5}])
    asyncio.run(on_rate_agents(session, payload))
    assert sent[-1] == {"type": "rating_result", "error": None}
    asyncio.run(on_rate_agents(session, payload))
    assert sent[-1] == {"type": "rating_result", "error": ratings.ALREADY_RATED}


# --- RGPD -------------------------------------------------------------------------------------

def test_account_deletion_keeps_the_score_without_account_nor_comment(db, sent):
    save_ratings(finished(account()), notes(("p1", 4, "Mon prénom est Vesper Dupont")))
    service.delete_account(db, service.find_by_pseudo(db, "Vesper"))
    db.expire_all()
    rating = db.query(AgentRating).one()
    assert (rating.user_id, rating.comment, rating.score, rating.agent) == (None, None, 4, "marIA")


def test_comments_are_erased_after_six_months_scores_are_kept(db, sent):
    save_ratings(finished(account()), notes(("p1", 4, "Ancien"), ("p2", 2, "Récent")))
    old, recent = db.query(AgentRating).order_by(AgentRating.id).all()
    now = utcnow()
    old.created_at = now - timedelta(days=184)
    recent.created_at = now - timedelta(days=100)
    db.commit()

    service.delete_expired_records(db, now=now)

    db.expire_all()
    assert [(r.score, r.comment) for r in db.query(AgentRating).order_by(AgentRating.id)] == [(4, None), (2, "Récent")]


def test_export_contains_the_player_ratings(db, sent):
    from backend.stats.queries import export_account
    save_ratings(finished(account()), notes(("p1", 4, "Bien joué")))
    exported = export_account(db, service.find_by_pseudo(db, "Vesper"))
    assert [{k: v for k, v in r.items() if k != "date"} for r in exported["agent_ratings"]] == [
        {"agent": "marIA", "score": 4, "comment": "Bien joué"}]


# --- Panel admin -------------------------------------------------------------------------------

def test_admin_sees_averages_by_personality_and_model(client, sent):
    first = finished(account("Vesper"))
    says(first, "p1", FAST)
    says(first, "p2", OTHER)
    save_ratings(first, notes(("p1", 5, "Parfait"), ("p2", 2, None), ("p3", 3, None)))
    second = finished(account("Orphee"))
    says(second, "p1", FAST)
    save_ratings(second, notes(("p1", 2, None)))
    personality = {pid: first.agents[pid].personality_key for pid in ("p1", "p2", "p3")}
    assert second.agents["p1"].personality_key == personality["p1"]  # même graine : mêmes personnalités

    data = admin(client).get("/admin/ratings").json()

    assert (data["count"], data["average"]) == (4, 3.0)
    by_personality = {row["key"]: (row["average"], row["count"]) for row in data["by_personality"]}
    assert by_personality == {personality["p1"]: (3.5, 2), personality["p2"]: (2.0, 1), personality["p3"]: (3.0, 1)}
    assert data["by_personality"][0]["key"] == personality["p1"]  # de la meilleure à la moins bonne
    by_model = {row["key"]: (row["average"], row["count"]) for row in data["by_model"]}
    assert by_model == {FAST: (3.5, 2), OTHER: (2.0, 1), None: (3.0, 1)}
    assert len(data["comments"]) == 1
    comment = data["comments"][0]
    assert (comment["agent"], comment["score"], comment["comment"], comment["author"]) == ("marIA", 5, "Parfait", "Vesper")
    assert comment["game_link"] == "detail"


def test_ratings_route_is_reserved_to_the_admin(client):
    assert client.get("/admin/ratings").status_code == 401
