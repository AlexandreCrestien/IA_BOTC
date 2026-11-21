"""Outils communs aux tests du backend."""
import pytest

from backend.server.session import set_current_session


@pytest.fixture
def clean_server():
    """Aucune partie en cours au début et à la fin du test."""
    set_current_session(None)
    yield
    set_current_session(None)
