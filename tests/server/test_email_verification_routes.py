"""Vérification de l'adresse e-mail côté serveur : routes, accès bloqués tant qu'elle n'est pas vérifiée,
jeu avec un compte non vérifié, purge à 72 heures."""
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.accounts import service
from backend.db import get_session
from backend.db.models import utcnow
from backend.server import game_runner as gr
from backend.server.app import app
from backend.server.session import GameSession, set_current_session


@pytest.fixture
def client(clean_server):
    with TestClient(app) as client:
        yield client


def register(client, pseudo="Vesper", email="vesper@exemple.fr"):
    return client.post("/api/auth/register", json={"pseudo": pseudo, "email": email, "password": "mot-de-passe"})


def token_in(mail) -> str:
    return re.search(r"verify-email\.html\?token=(\S+)", mail.body).group(1)


def user(pseudo="Vesper"):
    with get_session() as db:
        return service.find_by_pseudo(db, pseudo)


def test_registration_sends_a_verification_link(client, outbox):
    body = register(client).json()
    assert body["email_verified"] is False
    assert [m.to for m in outbox] == ["vesper@exemple.fr"]
    assert "confirmez votre adresse" in outbox[0].subject and "24 heures" in outbox[0].body
    assert "72 heures" in outbox[0].body


def test_dashboard_and_profile_wait_for_the_verification(client):
    register(client)
    for method, url, payload in [("get", "/api/me/stats", None), ("get", "/api/me/games", None),
                                 ("get", "/api/me/achievements", None), ("post", "/api/game/abandon", None),
                                 ("patch", "/api/account/pseudo", {"current_password": "mot-de-passe", "pseudo": "Ombre"})]:
        response = client.request(method.upper(), url, json=payload)
        assert response.status_code == 403, url
        assert "Confirmez d'abord votre adresse" in response.json()["detail"]
    # Toujours possibles : voir son compte, ses données, supprimer son compte
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/me/export").status_code == 200


def test_verification_link_unlocks_the_account(client, outbox):
    register(client)
    other_device = TestClient(app)  # le lien peut être ouvert ailleurs, sans être connecté
    response = other_device.post("/api/auth/verify-email", json={"token": token_in(outbox[0])})
    assert response.status_code == 200 and response.json()["pseudo"] == "Vesper"
    assert client.get("/api/auth/me").json()["email_verified"] is True
    assert client.get("/api/me/stats").status_code == 200
    again = other_device.post("/api/auth/verify-email", json={"token": token_in(outbox[0])})
    assert again.status_code == 400


def test_resend_link_is_limited(client, outbox):
    register(client)
    for _ in range(3):
        assert client.post("/api/account/verification-email").status_code == 200
    assert client.post("/api/account/verification-email").status_code == 429
    assert len(outbox) == 4  # inscription + 3 renvois


def test_resend_link_when_already_verified(client, outbox):
    register(client)
    client.post("/api/auth/verify-email", json={"token": token_in(outbox[0])})
    response = client.post("/api/account/verification-email")
    assert response.status_code == 400 and response.json()["detail"] == "Votre adresse e-mail est déjà vérifiée."


def test_forgot_password_never_writes_to_an_unverified_address(client, outbox):
    register(client)
    outbox.clear()
    response = client.post("/api/auth/forgot-password", json={"email": "vesper@exemple.fr"})
    assert "Si un compte existe" in response.json()["message"]  # même réponse
    assert outbox == []


def test_typo_at_signup_is_corrected_from_the_account(client, outbox):
    register(client, email="vespre@exemple.fr")
    response = client.patch("/api/account/email", json={"current_password": "mot-de-passe", "email": "vesper@exemple.fr"})
    assert response.json()["email"] == "vesper@exemple.fr" and response.json()["pending_email"] is None
    assert outbox[-1].to == "vesper@exemple.fr"
    client.post("/api/auth/verify-email", json={"token": token_in(outbox[-1])})
    assert client.get("/api/auth/me").json()["email_verified"] is True


def test_email_change_keeps_the_old_address_until_confirmed(client, outbox):
    register(client)
    client.post("/api/auth/verify-email", json={"token": token_in(outbox[0])})
    response = client.patch("/api/account/email", json={"current_password": "mot-de-passe", "email": "nouveau@exemple.fr"})
    assert (response.json()["email"], response.json()["pending_email"]) == ("vesper@exemple.fr", "nouveau@exemple.fr")
    assert outbox[-1].to == "nouveau@exemple.fr" and "nouvelle adresse" in outbox[-1].subject
    assert client.get("/api/auth/me").json()["pending_email"] == "nouveau@exemple.fr"
    client.post("/api/auth/verify-email", json={"token": token_in(outbox[-1])})
    me = client.get("/api/auth/me").json()
    assert (me["email"], me["pending_email"], me["email_verified"]) == ("nouveau@exemple.fr", None, True)


# --- Jouer avec un compte non vérifié ------------------------------------------------------------

def test_unverified_account_cannot_start_a_game(client):
    register(client)
    assert gr.can_join("Vesper", user()) == gr.REFUSED_UNVERIFIED


def test_unverified_account_can_finish_the_game_claimed_at_signup(client, monkeypatch):
    """Invité qui s'inscrit pendant sa partie : il la reprend même avant de vérifier son adresse."""
    register(client)
    monkeypatch.setattr(GameSession, "running", property(lambda self: True))
    set_current_session(GameSession(human_id="Lune", user_id=user().id))
    assert gr.can_join("Lune", user()) is None


def test_unverified_account_is_purged_after_72_hours(client):
    from backend.server.account_removal import purge_inactive_accounts
    register(client)
    register(TestClient(app), "Recent", "recent@exemple.fr")
    with get_session() as db:
        service.find_by_pseudo(db, "Vesper").created_at = utcnow() - timedelta(hours=73)
        db.commit()
    assert purge_inactive_accounts() == ["Vesper"]
    assert user("Recent") is not None


# --- Notifications de sécurité ----------------------------------------------------------------------

def verified_account(client, outbox):
    register(client)
    client.post("/api/auth/verify-email", json={"token": token_in(outbox[0])})
    outbox.clear()


def test_old_address_is_told_when_the_email_changes(client, outbox, monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "support@lantern-hollow.fr")
    verified_account(client, outbox)
    client.patch("/api/account/email", json={"current_password": "mot-de-passe", "email": "nouveau@exemple.fr"})
    client.post("/api/auth/verify-email", json={"token": token_in(outbox[-1])})

    notice = outbox[-1]
    assert notice.to == "vesper@exemple.fr" and "a changé" in notice.subject
    assert "n***@exemple.fr" in notice.body and "nouveau@exemple.fr" not in notice.body  # nouvelle adresse masquée
    assert "Contactez l'administrateur : support@lantern-hollow.fr" in notice.body


def test_password_change_is_notified(client, outbox):
    verified_account(client, outbox)
    client.patch("/api/account/password", json={"current_password": "mot-de-passe", "new_password": "nouveau-mdp"})
    assert [m.to for m in outbox] == ["vesper@exemple.fr"]
    assert "depuis votre profil" in outbox[0].body and "déconnectés" in outbox[0].body
    assert "Contactez l'administrateur du jeu." in outbox[0].body  # pas d'adresse de contact configurée


def test_password_reset_by_link_is_notified(client, outbox):
    verified_account(client, outbox)
    client.post("/api/auth/forgot-password", json={"email": "vesper@exemple.fr"})
    token = re.search(r"reset-password\.html\?token=(\S+)", outbox[-1].body).group(1)
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "nouveau-mdp"})
    assert "mot de passe oublié" in outbox[-1].body and "a été modifié" in outbox[-1].subject


def test_admin_reset_is_notified_with_the_admin_email_as_contact(monkeypatch, clean_server, outbox):
    monkeypatch.setenv("ADMIN_PSEUDO", "Gardien")
    monkeypatch.setenv("ADMIN_PASSWORD", "mot-de-passe-admin")
    monkeypatch.setenv("ADMIN_EMAIL", "gardien@exemple.fr")
    with TestClient(app) as admin:
        verified_account(TestClient(app), outbox)
        admin.post("/api/auth/login", json={"login": "Gardien", "password": "mot-de-passe-admin"})
        admin.post(f"/admin/users/{user().id}/reset-password")
    assert "par l'administrateur" in outbox[-1].body
    assert "Contactez l'administrateur : gardien@exemple.fr" in outbox[-1].body


def test_unverified_address_gets_no_notification(client, outbox):
    register(client)
    outbox.clear()
    client.patch("/api/account/email", json={"current_password": "mot-de-passe", "email": "autre@exemple.fr"})
    assert [m.subject for m in outbox] == ["Lantern Hollow : confirmez votre adresse e-mail"]  # seul le lien
