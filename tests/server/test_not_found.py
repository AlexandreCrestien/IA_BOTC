"""Adresse inconnue : page 404 du jeu pour le navigateur, JSON pour l'API, 404 simple pour un fichier manquant."""
import pytest
from fastapi.testclient import TestClient

from backend.server.app import app

BROWSER = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


@pytest.fixture
def client(clean_server):
    return TestClient(app)


@pytest.mark.parametrize("path", ["/page-inexistante", "/village/maison", "/ancienne-page.html"])
def test_unknown_page_shows_the_game_404_page(client, path):
    response = client.get(path, headers=BROWSER)
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Ce chemin ne mène nulle part" in response.text


@pytest.mark.parametrize("path", ["/api/inexistante", "/admin/inexistante"])
def test_unknown_api_route_stays_json(client, path):
    response = client.get(path, headers=BROWSER)
    assert response.status_code in (401, 404)  # /admin/… : connexion demandée avant tout
    assert response.headers["content-type"].startswith("application/json")


def test_api_not_found_keeps_its_message(client):
    response = client.post("/api/game/abandon", headers=BROWSER)
    assert response.status_code == 401
    assert response.json() == {"detail": "Vous n'êtes pas connecté."}


def test_missing_file_is_a_plain_404(client):
    response = client.get("/js/inexistant.js", headers=BROWSER)
    assert response.status_code == 404
    assert "Ce chemin ne mène nulle part" not in response.text


def test_non_browser_client_gets_json(client):
    response = client.get("/page-inexistante", headers={"accept": "application/json"})
    assert response.status_code == 404 and response.json() == {"detail": "Not Found"}


def test_existing_pages_are_untouched(client):
    for path in ("/", "/dashboard.html", "/admin"):
        assert client.get(path, headers=BROWSER).status_code == 200, path
