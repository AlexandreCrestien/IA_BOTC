"""Outils communs aux tests du backend."""
import pytest

from backend.server import websockets as ws


@pytest.fixture
def clean_server():
    """Le serveur ne garde rien d'un test à l'autre : données par joueur et rôles envoyés."""
    def clear():
        for store in ws.PLAYER_STORES:
            store.clear()
        ws.roles_sent.clear()

    clear()
    yield
    clear()
