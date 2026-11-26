"""Connexion à la base et migrations.

L'adresse vient de DATABASE_URL (.env) :
- PostgreSQL (recommandé) : postgresql+psycopg://…, base lancée avec `docker compose up -d` (docker-compose.yml) ;
- à défaut, un fichier SQLite data/lantern_hollow.db (sans Docker, pour essayer le jeu rapidement).
Le code passe par SQLAlchemy : il est le même pour les deux bases.

init_db() est appelée au démarrage du serveur : elle applique les migrations Alembic
(backend/db/migrations) puis clôt les parties restées en cours. Les tests l'appellent avec une base en mémoire.
"""
import logging
import os
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.games import interrupt_unfinished_games

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_URL = "sqlite:///data/lantern_hollow.db"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

LEGACY_DATABASE = ("La base {url} a été créée par une version précédente du jeu, avant les migrations Alembic. "
                   "Supprimez-la (elle sera recréée au démarrage) ou utilisez PostgreSQL (voir docs/configuration.md).")

DATABASE_UNREACHABLE = ("Base de données injoignable ({url}). Si elle tourne avec Docker, lancez-la : "
                        "`docker compose up -d` (état : `docker compose ps`), puis relancez le serveur.")


class DatabaseUnavailable(RuntimeError):
    """La base ne répond pas (PostgreSQL pas lancé, mauvais port…) : message à afficher tel quel."""


_engine: Optional[Engine] = None
_sessions = sessionmaker(expire_on_commit=False)


def database_url(url: Optional[str] = None) -> str:
    """Adresse de la base : celle donnée, sinon DATABASE_URL, sinon le fichier SQLite par défaut."""
    return url or os.getenv("DATABASE_URL") or DEFAULT_URL


def _create_engine(url: str) -> Engine:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        # pool_pre_ping : une connexion coupée (base redémarrée) est remplacée au lieu de faire échouer la requête
        # connect_timeout : base injoignable signalée en quelques secondes
        return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})

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


def check_database(url: Optional[str] = None) -> None:
    """Vérifie que la base répond, avant de lancer le serveur (main.py). Lève DatabaseUnavailable sinon."""
    url = database_url(url)
    engine = _create_engine(url)
    try:
        with engine.connect():
            pass
    except OperationalError as error:
        raise DatabaseUnavailable(DATABASE_UNREACHABLE.format(url=make_url(url).render_as_string(hide_password=True))) \
            from error
    finally:
        engine.dispose()


def migrate(engine: Engine) -> None:
    """Applique les migrations Alembic qui manquent (base vide : création de toutes les tables)."""
    try:
        tables = set(inspect(engine).get_table_names())
    except OperationalError as error:
        url = engine.url.render_as_string(hide_password=True)
        raise DatabaseUnavailable(DATABASE_UNREACHABLE.format(url=url)) from error
    if "users" in tables and "alembic_version" not in tables:
        raise RuntimeError(LEGACY_DATABASE.format(url=engine.url.render_as_string(hide_password=True)))
    config = Config(str(ALEMBIC_INI))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def init_db(url: Optional[str] = None) -> Engine:
    """Ouvre la base, applique les migrations et clôt les parties restées en cours
    (le serveur s'est arrêté pendant une partie : elles deviennent « interrompues »)."""
    global _engine
    url = database_url(url)
    if _engine is not None:
        _engine.dispose()
    _engine = _create_engine(url)
    migrate(_engine)
    _sessions.configure(bind=_engine)

    with get_session() as db:
        interrupted = interrupt_unfinished_games(db)
        db.commit()
    if interrupted:
        logger.info("%d partie(s) restée(s) en cours marquée(s) comme interrompue(s)", interrupted)
    logger.info("Base de données prête : %s", make_url(url).render_as_string(hide_password=True))
    return _engine


def get_session() -> Session:
    """Nouvelle session de base, à utiliser avec « with get_session() as db: » puis db.commit().
    Le serveur ouvre la base au démarrage ; à défaut (scripts, tests), elle est ouverte au premier usage."""
    if _engine is None:
        init_db()
    return _sessions()
