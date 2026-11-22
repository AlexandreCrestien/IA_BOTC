"""Connexion à la base (SQLite pour l'instant) et création des tables.

L'adresse vient de DATABASE_URL (.env), par défaut un fichier data/lantern_hollow.db.
Le code passe par SQLAlchemy : changer de base (PostgreSQL…) revient à changer l'adresse et le driver.
init_db() est appelée au démarrage du serveur ; les tests l'appellent avec une base en mémoire.
"""
import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.games import interrupt_unfinished_games
from backend.db.models import Base

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
