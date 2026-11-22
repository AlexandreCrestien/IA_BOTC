"""Outils communs aux tests du backend."""
import os

# Base en mémoire pour tous les tests (y compris le démarrage de l'application) : la vraie base n'est jamais touchée
os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402

from backend.db import get_session, init_db  # noqa: E402
from backend.server.session import set_current_session  # noqa: E402


@pytest.fixture
def clean_server():
    """Aucune partie en cours au début et à la fin du test."""
    set_current_session(None)
    yield
    set_current_session(None)


@pytest.fixture
def db():
    """Base en mémoire, vide, avec ses tables ; session ouverte pendant le test."""
    init_db("sqlite://")
    with get_session() as session:
        yield session
