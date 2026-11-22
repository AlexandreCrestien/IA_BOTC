"""Base de données : création des tables, contraintes, parties restées en cours au démarrage."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend.db import GameRecord, GameStatus, UnlockedAchievement, User, get_session, init_db, pseudo_key
from backend.models import Alignment, RoleKey


def make_user(pseudo: str = "Vesper") -> User:
    return User(pseudo=pseudo, password_hash="hash")


def make_game(user: User, status: GameStatus = GameStatus.IN_PROGRESS) -> GameRecord:
    return GameRecord(user=user, role=RoleKey.VALET, alignment=Alignment.GOOD, status=status)


def test_tables_are_created(db):
    tables = set(inspect(db.get_bind()).get_table_names())
    assert {"users", "games", "unlocked_achievements"} <= tables


def test_new_user_defaults(db):
    user = make_user()
    db.add(user)
    db.commit()
    assert user.id is not None
    assert user.is_admin is False
    assert user.token_version == 0
    assert user.created_at is not None
    assert user.pseudo_key == "vesper"


def test_pseudo_key_follows_pseudo_changes(db):
    user = make_user("Vesper")
    db.add(user)
    db.commit()
    user.pseudo = "Ombre"
    db.commit()
    assert db.scalar(select(User).where(User.pseudo_key == pseudo_key("OMBRE"))) is user


def test_pseudo_is_unique_whatever_the_case(db):
    db.add(make_user("Vesper"))
    db.commit()
    db.add(make_user("vESPER"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_game_stores_enum_values(db):
    """Les colonnes gardent la valeur lisible ("valet", "good"…), pas le nom Python de l'énumération."""
    db.add(make_game(make_user()))
    db.commit()
    row = db.execute(text("SELECT role, alignment, status FROM games")).one()
    assert tuple(row) == ("valet", "good", "in_progress")
    game = db.scalar(select(GameRecord))
    assert game.role is RoleKey.VALET and game.alignment is Alignment.GOOD
    assert game.turns == 0 and game.ended_at is None and game.started_at is not None


def test_game_requires_an_account(db):
    """Les parties des invités ne sont pas enregistrées : une partie a toujours un compte."""
    db.add(GameRecord(role=RoleKey.VALET, alignment=Alignment.GOOD))
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_keys_are_enforced(db):
    db.add(GameRecord(user_id=999, role=RoleKey.REAPER, alignment=Alignment.EVIL))
    with pytest.raises(IntegrityError):
        db.commit()


def test_achievement_unlocked_once_per_user(db):
    user = make_user()
    db.add_all([user, UnlockedAchievement(user=user, code="win_valet")])
    db.commit()
    db.add(UnlockedAchievement(user=user, code="win_valet"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_same_achievement_for_two_users(db):
    first, second = make_user("Vesper"), make_user("Ombre")
    db.add_all([UnlockedAchievement(user=first, code="win_valet"), UnlockedAchievement(user=second, code="win_valet")])
    db.commit()
    assert len(db.scalars(select(UnlockedAchievement)).all()) == 2


def test_startup_interrupts_games_left_in_progress(tmp_path):
    """Le serveur s'est arrêté pendant une partie : au redémarrage, elle est « interrompue », les autres ne bougent pas."""
    url = f"sqlite:///{tmp_path / 'sub' / 'test.db'}"  # le dossier parent est créé
    init_db(url)
    with get_session() as db:
        user = make_user()
        db.add_all([make_game(user), make_game(user, GameStatus.WON), make_game(user, GameStatus.ABANDONED)])
        db.commit()

    init_db(url)  # redémarrage
    with get_session() as db:
        games = db.scalars(select(GameRecord).order_by(GameRecord.id)).all()
        assert [g.status for g in games] == [GameStatus.INTERRUPTED, GameStatus.WON, GameStatus.ABANDONED]
        assert games[0].ended_at is not None
        assert games[1].ended_at is None  # les parties terminées ne sont pas modifiées
    init_db("sqlite://")  # libère le fichier


def test_application_startup_opens_the_database():
    """Le démarrage du serveur initialise la base (en mémoire pendant les tests : DATABASE_URL de conftest)."""
    from backend.server.app import app
    with TestClient(app):
        with get_session() as db:
            db.add(make_user())
            db.commit()
            assert db.scalar(select(User)).pseudo == "Vesper"
