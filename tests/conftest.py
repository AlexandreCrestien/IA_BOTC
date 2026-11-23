"""Outils communs aux tests du backend."""
import os

from dotenv import load_dotenv

# Base des tests : SQLite en mémoire (rapide, sans Docker), ou PostgreSQL si TEST_DATABASE_URL est défini
# (base dédiée, vidée avant chaque test). La base du jeu (DATABASE_URL du .env) n'est jamais touchée.
load_dotenv()
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or "sqlite://"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Comptes : clé de test, hachage rapide, et pas de compte admin venu du vrai .env
# (load_dotenv ne remplace pas une variable déjà définie, même vide)
os.environ["JWT_SECRET"] = "cle-de-test-uniquement-pour-pytest-0123456789"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["ADMIN_PSEUDO"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["ADMIN_EMAIL"] = ""
# E-mails gardés en mémoire (backend.mail.OUTBOX), jamais envoyés ni affichés
os.environ["MAIL_MODE"] = "memory"

import pytest  # noqa: E402

from backend.db import get_session, init_db  # noqa: E402
from backend.server.session import set_current_session  # noqa: E402


@pytest.fixture
def clean_server():
    """Aucune partie en cours au début et à la fin du test."""
    set_current_session(None)
    yield
    set_current_session(None)


def _on_postgres() -> bool:
    return TEST_DATABASE_URL.startswith("postgresql")


def _empty_test_database() -> None:
    """Vide la base PostgreSQL de test : tables et version des migrations (schéma public recréé)."""
    from sqlalchemy import create_engine
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
    engine.dispose()


@pytest.fixture(autouse=True)
def fresh_test_database():
    """Tests sur PostgreSQL : chaque test repart d'une base vide, comme avec une base SQLite en mémoire."""
    if _on_postgres():
        _empty_test_database()
        init_db(TEST_DATABASE_URL)
    yield


@pytest.fixture
def db():
    """Base de test vide, avec ses tables ; session ouverte pendant le test."""
    if _on_postgres():
        _empty_test_database()
    init_db(TEST_DATABASE_URL)
    with get_session() as session:
        yield session


@pytest.fixture(autouse=True)
def reset_login_limiter():
    """Les échecs de connexion et les demandes de mot de passe oublié sont gardés en mémoire par le serveur :
    on repart de zéro à chaque test."""
    from backend.server.auth import login_limiter, reset_limiter
    for limiter in (login_limiter, reset_limiter):
        limiter.failures.clear()
    yield
    for limiter in (login_limiter, reset_limiter):
        limiter.failures.clear()


@pytest.fixture(autouse=True)
def outbox():
    """E-mails « envoyés » pendant le test (MAIL_MODE=memory)."""
    from backend.mail import OUTBOX
    OUTBOX.clear()
    yield OUTBOX
    OUTBOX.clear()
