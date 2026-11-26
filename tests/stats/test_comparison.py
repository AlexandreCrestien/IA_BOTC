"""Comparaison aux autres joueurs (moyennes, part des joueurs par succès) et joueurs de démonstration."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.db import GameRecord, GameStatus, UnlockedAchievement, User
from backend.db.models import utcnow
from backend.models import Alignment, RoleKey
from backend.stats.queries import MIN_PLAYERS_FOR_COMPARISON, community_comparison

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from demo_players import DEMO_DOMAIN, add_demo_players, remove_demo_players  # noqa: E402

SIDES = {RoleKey.MEDIUM: Alignment.GOOD, RoleKey.REAPER: Alignment.EVIL}


def player(db, pseudo, admin=False) -> User:
    user = User(pseudo=pseudo, password_hash="hash", email=f"{pseudo.lower()}@exemple.fr", is_admin=admin,
                email_verified_at=utcnow())
    db.add(user)
    db.commit()
    return user


def game(db, user_id, role=RoleKey.MEDIUM, status=GameStatus.WON, turns=3):
    db.add(GameRecord(user_id=user_id, role=role, alignment=SIDES[role], status=status, turns=turns))
    db.commit()


def players_with_one_game(db, count, **game_options) -> list[User]:
    users = [player(db, f"Joueur{i}") for i in range(count)]
    for user in users:
        game(db, user.id, **game_options)
    return users


def test_no_comparison_under_10_players(db):
    players_with_one_game(db, MIN_PLAYERS_FOR_COMPARISON - 1)
    result = community_comparison(db)
    assert result == {"available": False, "players": 9, "min_players": 10}


def test_averages_from_10_players(db):
    users = players_with_one_game(db, 10)  # 10 victoires du Médium en 3 tours
    game(db, users[0].id, RoleKey.REAPER, GameStatus.LOST, turns=5)
    game(db, users[1].id, RoleKey.REAPER, GameStatus.ABANDONED, turns=1)
    game(db, users[2].id, status=GameStatus.INTERRUPTED)  # hors statistiques
    averages = community_comparison(db)["averages"]
    assert averages["played"] == 1.2                       # 12 parties comptées pour 10 joueurs
    assert averages["win_rate"] == round(10 / 12, 3)
    assert (averages["good_win_rate"], averages["evil_win_rate"]) == (1.0, 0.0)
    assert averages["average_turns"] == round((10 * 3 + 5 + 1) / 12, 1)


def test_admin_is_left_out_and_anonymous_games_count(db):
    players_with_one_game(db, 9)
    admin = player(db, "Gardien", admin=True)
    game(db, admin.id)
    assert community_comparison(db)["available"] is False  # l'admin ne compte pas comme joueur
    player_ten = player(db, "Dixieme")
    game(db, player_ten.id)
    db.add(GameRecord(user_id=None, role=RoleKey.REAPER, alignment=Alignment.EVIL, status=GameStatus.LOST, turns=4))
    db.commit()
    averages = community_comparison(db)["averages"]
    assert averages["evil_win_rate"] == 0.0  # la partie anonymisée compte, celle de l'admin non


def test_achievement_percentages(db):
    users = players_with_one_game(db, 10)
    for user in users[:3]:
        db.add(UnlockedAchievement(user_id=user.id, code="win_medium"))
    db.add(UnlockedAchievement(user_id=users[0].id, code="one_turn_win"))
    db.commit()
    percents = community_comparison(db)["achievements"]
    assert (percents["win_medium"], percents["one_turn_win"], percents["executed"]) == (30, 10, 0)
    assert len(percents) == 14


# --- Joueurs de démonstration ----------------------------------------------------------------------------

def test_demo_players_make_the_comparison_available(db):
    real = player(db, "Vesper")
    assert len(add_demo_players(db)) == 10
    assert add_demo_players(db) == []  # pas de doublons
    demo = db.query(User).filter(User.email.like(f"%@{DEMO_DOMAIN}")).all()
    assert all(u.email_verified and not u.is_admin for u in demo)
    assert community_comparison(db)["available"] is True

    assert len(remove_demo_players(db)) == 10
    assert db.query(User).all() == [real]
    assert db.query(GameRecord).count() == 0 and db.query(UnlockedAchievement).count() == 0  # rien ne reste


def test_demo_players_are_reproducible(db):
    add_demo_players(db)
    first = sorted((g.role.value, g.status.value, g.turns) for g in db.query(GameRecord))
    remove_demo_players(db)
    add_demo_players(db)
    assert sorted((g.role.value, g.status.value, g.turns) for g in db.query(GameRecord)) == first


def test_comparison_route(clean_server):
    from backend.db import get_session
    from backend.server.app import app
    with TestClient(app) as client:
        client.post("/api/auth/register", json={"pseudo": "Vesper", "email": "vesper@exemple.fr",
                                                "password": "mot-de-passe"})
        assert client.get("/api/me/comparison").status_code == 403  # adresse pas encore confirmée
        with get_session() as db:  # adresse confirmée, comme si le lien reçu par e-mail avait été ouvert
            db.query(User).filter_by(pseudo="Vesper").one().email_verified_at = utcnow()
            db.commit()
        body = client.get("/api/me/comparison").json()
        assert body["available"] is False and body["min_players"] == 10
