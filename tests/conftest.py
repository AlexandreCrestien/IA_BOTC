"""Outils communs aux tests du backend."""
import os

# Base en mémoire pour tous les tests (y compris le démarrage de l'application) : la vraie base n'est jamais touchée
os.environ["DATABASE_URL"] = "sqlite://"
# Comptes : clé de test, hachage rapide, et pas de compte admin venu du vrai .env
# (load_dotenv ne remplace pas une variable déjà définie, même vide)
os.environ["JWT_SECRET"] = "cle-de-test-uniquement-pour-pytest-0123456789"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ADMIN_PSEUDO"] = ""
os.environ["ADMIN_PASSWORD"] = ""

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


@pytest.fixture(autouse=True)
def reset_login_limiter():
    """Les échecs de connexion sont gardés en mémoire par le serveur : on repart de zéro à chaque test."""
    from backend.server.auth import login_limiter
    login_limiter.failures.clear()
    yield
    login_limiter.failures.clear()
