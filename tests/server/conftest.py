"""Fixtures communes aux tests du serveur (les modules qui définissent leur propre fixture du même nom la gardent)."""
import pytest
from fastapi.testclient import TestClient

from backend.server import protocol
from backend.server.app import app


@pytest.fixture
def client(clean_server, monkeypatch):
    """Client HTTP du serveur, avec un compte admin (Gardien / mot-de-passe-admin) créé au démarrage."""
    monkeypatch.setenv("ADMIN_PSEUDO", "Gardien")
    monkeypatch.setenv("ADMIN_PASSWORD", "mot-de-passe-admin")
    monkeypatch.setenv("ADMIN_EMAIL", "gardien@exemple.fr")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sent(monkeypatch):
    """Messages envoyés au front pendant le test."""
    messages = []

    async def fake_send(player_id, message):
        messages.append(message)

    monkeypatch.setattr(protocol.manager, "send_to_player", fake_send)
    return messages
