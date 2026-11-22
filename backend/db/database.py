"""Connexion à la base (SQLite pour l'instant) et création des tables.

L'adresse vient de DATABASE_URL (.env), par défaut un fichier data/lantern_hollow.db.
Le code passe par SQLAlchemy : changer de base (PostgreSQL…) revient à changer l'adresse et le driver.
init_db() est appelée au démarrage du serveur ; les tests l'appellent avec une base en mémoire.
"""
import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, MetaData, create_engine, event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.games import interrupt_unfinished_games
from backend.db.models import Base, GameRecord, User

logger = logging.getLogger(__name__)

DEFAULT_URL = "sqlite:///data/lantern_hollow.db"

_engine: Optional[Engine] = None
_sessions = sessionmaker(expire_on_commit=False)


def _create_engine(url: str) -> Engine:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return create_engine(url)

    # Le serveur appelle la base depuis plusieurs threads (routes FastAPI)
    options = {"connect_args": {"check_same_thread": False}}
    if parsed.database in (None, "", ":memory:"):
        # Base en mémoire (tests) : une seule connexion partagée, sinon chaque connexion aurait sa base vide
        options["poolclass"] = StaticPool
    else:
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        # SQLite n'applique les clés étrangères que si on le lui demande, à chaque connexion
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def init_db(url: Optional[str] = None) -> Engine:
    """Ouvre la base, crée les tables manquantes et clôt les parties restées en cours
    (le serveur s'est arrêté pendant une partie : elles deviennent « interrompues »)."""
    global _engine
    url = url or os.getenv("DATABASE_URL") or DEFAULT_URL
    if _engine is not None:
        _engine.dispose()
    _engine = _create_engine(url)
    Base.metadata.create_all(_engine)
    _upgrade_schema(_engine)
    _sessions.configure(bind=_engine)

    with get_session() as db:
        interrupted = interrupt_unfinished_games(db)
        db.commit()
    if interrupted:
        logger.info("%d partie(s) restée(s) en cours marquée(s) comme interrompue(s)", interrupted)
    logger.info("Base de données prête : %s", make_url(url).render_as_string(hide_password=True))
    return _engine


def _upgrade_schema(engine: Engine) -> None:
    """Met à niveau une base créée par une version précédente (create_all ne modifie pas les tables existantes).
    Mise à niveau provisoire, à remplacer par des migrations Alembic (axe d'amélioration) :
    - users.last_seen_at : ajoutée, remplie avec la date de création ;
    - games.user_id : devient facultatif (parties anonymisées). SQLite ne sait pas modifier une colonne :
      la table est recréée et ses lignes recopiées."""
    columns = {c["name"] for c in inspect(engine).get_columns("users")}
    if "last_seen_at" not in columns:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN last_seen_at DATETIME")
            conn.exec_driver_sql("UPDATE users SET last_seen_at = created_at")
        logger.info("Base mise à niveau : users.last_seen_at")

    user_id = next(c for c in inspect(engine).get_columns("games") if c["name"] == "user_id")
    if user_id["nullable"] or engine.dialect.name != "sqlite":
        return
    metadata = MetaData()
    User.__table__.to_metadata(metadata)  # cible de la clé étrangère
    new_games = GameRecord.__table__.to_metadata(metadata, name="games_new")
    new_games.indexes.clear()  # recréés après le renommage (mêmes noms que ceux de l'ancienne table)
    names = ", ".join(column.name for column in new_games.columns)
    with engine.connect() as conn:
        # Clés étrangères suspendues pendant la recopie (sans effet si une transaction est ouverte : commit avant)
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.commit()
        with conn.begin():
            new_games.create(conn)
            conn.exec_driver_sql(f"INSERT INTO games_new ({names}) SELECT {names} FROM games")
            conn.exec_driver_sql("DROP TABLE games")
            conn.exec_driver_sql("ALTER TABLE games_new RENAME TO games")
            for index in GameRecord.__table__.indexes:
                index.create(conn)
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.commit()
    logger.info("Base mise à niveau : games.user_id facultatif (parties anonymisées)")


def get_session() -> Session:
    """Nouvelle session de base, à utiliser avec « with get_session() as db: » puis db.commit().
    Le serveur ouvre la base au démarrage ; à défaut (scripts, tests), elle est ouverte au premier usage."""
    if _engine is None:
        init_db()
    return _sessions()
