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


def test_anonymized_game_has_no_account(db):
    """Après la suppression de son compte, une partie ne garde que son résumé, sans lien avec personne."""
    db.add(GameRecord(role=RoleKey.VALET, alignment=Alignment.GOOD, status=GameStatus.WON))
    db.commit()
    assert db.scalar(select(GameRecord)).user_id is None


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


OLD_SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY, pseudo VARCHAR(20) NOT NULL, pseudo_key VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(100) NOT NULL, is_admin BOOLEAN NOT NULL, token_version INTEGER NOT NULL,
    created_at DATETIME NOT NULL);
"""


def test_database_from_before_migrations_is_refused_clearly(tmp_path):
    """Base SQLite créée avant Alembic : message clair plutôt qu'une erreur SQL obscure."""
    import sqlite3
    path = tmp_path / "ancienne.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(OLD_SCHEMA)
    with pytest.raises(RuntimeError, match="version précédente du jeu"):
        init_db(f"sqlite:///{path}")
    init_db("sqlite://")


def test_migrations_match_the_models(db):
    """La dernière migration crée exactement les tables décrites dans models.py
    (sinon : oubli de `alembic revision --autogenerate` après un changement de modèle)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from backend.db.models import Base
    differences = compare_metadata(MigrationContext.configure(db.connection()), Base.metadata)
    assert differences == []


def test_migrations_can_be_rolled_back_and_replayed(tmp_path):
    from alembic import command
    from alembic.config import Config
    from backend.db.database import ALEMBIC_INI
    url = f"sqlite:///{tmp_path / 'aller-retour.db'}"
    engine = init_db(url)
    config = Config(str(ALEMBIC_INI))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    init_db(url)
    assert {"users", "games", "unlocked_achievements"} <= set(inspect(engine).get_table_names())
    init_db("sqlite://")


UNREACHABLE = "postgresql+psycopg://lantern:secret@localhost:1/lantern_hollow"  # aucun serveur sur le port 1


def test_unreachable_database_gives_a_clear_message():
    """PostgreSQL pas lancé (docker compose oublié) : message clair, sans le mot de passe."""
    from backend.db.database import DatabaseUnavailable, check_database
    with pytest.raises(DatabaseUnavailable) as error:
        check_database(UNREACHABLE)
    message = str(error.value)
    assert "docker compose up -d" in message
    assert "localhost:1" in message and "secret" not in message


def test_server_start_with_unreachable_database_gives_the_same_message():
    from backend.db.database import DatabaseUnavailable
    with pytest.raises(DatabaseUnavailable, match="docker compose up -d"):
        init_db(UNREACHABLE)
    init_db("sqlite://")


def test_reachable_database_passes_the_check():
    from backend.db.database import check_database
    check_database("sqlite://")
