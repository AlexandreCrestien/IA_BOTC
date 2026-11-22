"""Routes des comptes : inscription, connexion (cookie HttpOnly), déconnexion, profil, limitation des tentatives."""
import pytest
from fastapi.testclient import TestClient

from backend.accounts.tokens import COOKIE_NAME
from backend.server.app import app
from backend.server.auth import LoginLimiter


@pytest.fixture
def client(clean_server):
    with TestClient(app) as client:
        yield client


def register(client, pseudo="Vesper", password="mot-de-passe"):
    return client.post("/api/auth/register", json={"pseudo": pseudo, "password": password})


def login(client, pseudo="Vesper", password="mot-de-passe"):
    return client.post("/api/auth/login", json={"pseudo": pseudo, "password": password})


def test_register_logs_the_player_in(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["pseudo"] == "Vesper" and response.json()["is_admin"] is False
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert client.get("/api/auth/me").json()["pseudo"] == "Vesper"


def test_register_errors_are_explained(client):
    register(client)
    response = register(TestClient(app), "VESPER")
    assert (response.status_code, response.json()["detail"]) == (409, "Ce pseudo est déjà pris.")
    assert register(client, "Lord Ashcombe").status_code == 400
    assert "8 caractères" in register(client, "Ombre", "court").json()["detail"]


def test_login_and_logout(client):
    register(client)
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401

    assert login(client).status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert f'{COOKIE_NAME}=""' in response.headers["set-cookie"]  # cookie effacé
    assert client.get("/api/auth/me").status_code == 401


def test_login_does_not_reveal_whether_the_pseudo_exists(client):
    register(client)
    wrong_password, unknown = login(client, password="mauvais"), login(client, pseudo="Inconnu")
    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json() == unknown.json() == {"detail": "Pseudo ou mot de passe incorrect."}


def test_login_is_blocked_after_too_many_failures(client):
    register(client)
    for _ in range(LoginLimiter.MAX_FAILURES):
        assert login(client, password="mauvais").status_code == 401
    blocked = login(client)  # même le bon mot de passe est refusé pendant le blocage
    assert blocked.status_code == 429
    assert "Trop de tentatives" in blocked.json()["detail"]
    assert login(client, pseudo="Ombre").status_code == 401  # les autres pseudos ne sont pas bloqués


def test_success_clears_previous_failures(client):
    register(client)
    for _ in range(LoginLimiter.MAX_FAILURES - 1):
        login(client, password="mauvais")
    assert login(client).status_code == 200
    assert login(client, password="mauvais").status_code == 401  # le compteur est reparti de zéro


def test_limiter_forgets_old_failures(monkeypatch):
    limiter = LoginLimiter()
    now = [1000.0]
    monkeypatch.setattr("backend.server.auth.time.monotonic", lambda: now[0])
    for _ in range(LoginLimiter.MAX_FAILURES):
        limiter.failed("vesper")
    assert limiter.blocked("vesper")
    now[0] += LoginLimiter.WINDOW + 1
    assert not limiter.blocked("vesper")


def test_change_pseudo(client):
    register(client)
    response = client.patch("/api/account/pseudo", json={"current_password": "mot-de-passe", "pseudo": "Ombre"})
    assert response.status_code == 200 and response.json()["pseudo"] == "Ombre"
    assert client.get("/api/auth/me").json()["pseudo"] == "Ombre"
    wrong = client.patch("/api/account/pseudo", json={"current_password": "mauvais", "pseudo": "Lune"})
    assert (wrong.status_code, wrong.json()["detail"]) == (403, "Mot de passe actuel incorrect.")


def test_change_password_logs_out_other_devices(client):
    register(client)
    other_device = TestClient(app)
    login(other_device)

    response = client.patch("/api/account/password",
                            json={"current_password": "mot-de-passe", "new_password": "nouveau-mdp"})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200       # cet appareil reçoit un nouveau jeton
    assert other_device.get("/api/auth/me").status_code == 401  # les autres sont déconnectés
    assert login(TestClient(app), password="nouveau-mdp").status_code == 200


def test_profile_routes_require_a_login(client):
    assert client.patch("/api/account/pseudo", json={"current_password": "x", "pseudo": "Ombre"}).status_code == 401
    assert client.patch("/api/account/password", json={"current_password": "x", "new_password": "y"}).status_code == 401


def test_oversized_fields_are_rejected(client):
    assert register(client, "a" * 101).status_code == 422
    assert register(client, "Vesper", "a" * 201).status_code == 422


def test_admin_account_is_created_at_startup(monkeypatch, clean_server):
    monkeypatch.setenv("ADMIN_PSEUDO", "Gardien")
    monkeypatch.setenv("ADMIN_PASSWORD", "mot-de-passe-admin")
    with TestClient(app) as client:
        assert login(client, "Gardien", "mot-de-passe-admin").json()["is_admin"] is True
