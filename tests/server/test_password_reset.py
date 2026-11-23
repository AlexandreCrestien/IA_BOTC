"""Routes de l'e-mail : inscription, connexion par e-mail, mot de passe oublié, changement d'adresse,
avertissement par e-mail avant suppression ; et l'envoi lui-même (modes console, SMTP, mémoire)."""
import logging
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend import mail
from backend.accounts import service
from backend.db import get_session
from backend.db.models import utcnow
from backend.server.app import app


@pytest.fixture
def client(clean_server):
    with TestClient(app) as client:
        yield client


def register(client, pseudo="Vesper", email="vesper@exemple.fr", password="mot-de-passe"):
    return client.post("/api/auth/register", json={"pseudo": pseudo, "email": email, "password": password})


def login(client, identifier="Vesper", password="mot-de-passe"):
    return client.post("/api/auth/login", json={"login": identifier, "password": password})


def forgot(client, email="vesper@exemple.fr"):
    return client.post("/api/auth/forgot-password", json={"email": email})


def link_token(outbox) -> str:
    return re.search(r"reset-password\.html\?token=(\S+)", outbox[-1].body).group(1)


def test_register_requires_a_valid_email(client):
    assert register(client, email="").json()["detail"] == "Veuillez indiquer une adresse e-mail."
    assert register(client, email="pas-une-adresse").json()["detail"] == "Adresse e-mail invalide."
    response = register(client)
    assert response.status_code == 201 and response.json()["email"] == "vesper@exemple.fr"
    duplicate = register(TestClient(app), "Ombre", "VESPER@exemple.fr")
    assert duplicate.status_code == 409


def test_login_with_email(client):
    register(client)
    client.cookies.clear()
    assert login(client, "Vesper@Exemple.fr").status_code == 200
    assert client.get("/api/auth/me").json()["email"] == "vesper@exemple.fr"


def test_login_failures_are_counted_per_account(client):
    """Alterner pseudo et e-mail ne donne pas plus d'essais."""
    register(client)
    for identifier in ("Vesper", "vesper@exemple.fr", "Vesper", "vesper@exemple.fr", "Vesper"):
        login(client, identifier, "mauvais")
    assert login(client, "vesper@exemple.fr").status_code == 429


def test_forgot_password_sends_a_link_that_works_once(client, outbox):
    register(client)
    other_device = TestClient(app)
    login(other_device)

    response = forgot(client, "VESPER@exemple.fr")
    assert response.status_code == 200 and "Si un compte existe" in response.json()["message"]
    assert [m.to for m in outbox] == ["vesper@exemple.fr"]
    assert "Vesper" in outbox[0].body and "30 minutes" in outbox[0].body
    token = link_token(outbox)

    done = client.post("/api/auth/reset-password", json={"token": token, "new_password": "nouveau-mdp"})
    assert done.status_code == 200
    assert other_device.get("/api/auth/me").status_code == 401  # tous les appareils déconnectés
    assert login(TestClient(app), password="mot-de-passe").status_code == 401
    assert login(TestClient(app), password="nouveau-mdp").status_code == 200
    again = client.post("/api/auth/reset-password", json={"token": token, "new_password": "encore-un"})
    assert again.status_code == 400 and "plus valable" in again.json()["detail"]


def test_forgot_password_does_not_reveal_unknown_addresses(client, outbox):
    register(client)
    known, unknown = forgot(client), forgot(client, "inconnu@exemple.fr")
    assert known.json() == unknown.json()
    assert [m.to for m in outbox] == ["vesper@exemple.fr"]


def test_forgot_password_is_limited(client, outbox):
    register(client)
    for _ in range(5):
        assert forgot(client).status_code == 200  # même réponse, mais pas plus de 3 e-mails
    assert len(outbox) == 3


def test_change_email_route(client):
    register(client)
    wrong = client.patch("/api/account/email", json={"current_password": "mauvais", "email": "n@exemple.fr"})
    assert wrong.status_code == 403
    response = client.patch("/api/account/email", json={"current_password": "mot-de-passe", "email": "N@Exemple.fr"})
    assert response.status_code == 200 and response.json()["email"] == "n@exemple.fr"


def test_export_contains_the_email(client):
    register(client)
    assert client.get("/api/me/export").json()["account"]["email"] == "vesper@exemple.fr"


def test_inactive_account_is_warned_by_email(client, outbox):
    from backend.server.account_removal import purge_inactive_accounts
    register(client)
    with get_session() as db:
        service.find_by_pseudo(db, "Vesper").last_seen_at = utcnow() - timedelta(days=340)
        db.commit()
    assert purge_inactive_accounts() == []  # prévenu, pas supprimé
    assert outbox[-1].to == "vesper@exemple.fr" and "bientôt supprimé" in outbox[-1].subject
    assert "Vesper" in outbox[-1].body
    purge_inactive_accounts()
    assert len(outbox) == 1  # une seule fois


# --- Envoi des e-mails ---------------------------------------------------------------------------

def test_console_mode_prints_the_email(monkeypatch, caplog):
    monkeypatch.setenv("MAIL_MODE", "console")
    with caplog.at_level(logging.INFO, logger="backend.mail"):
        assert mail.send_mail("vesper@exemple.fr", "Objet", "Lien : http://exemple/x")
    assert "vesper@exemple.fr" in caplog.text and "http://exemple/x" in caplog.text


def test_smtp_failure_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setenv("MAIL_MODE", "smtp")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_PORT", "1")  # aucun serveur
    with caplog.at_level(logging.ERROR, logger="backend.mail"):
        assert mail.send_mail("vesper@exemple.fr", "Objet", "Texte") is False
    assert "Échec de l'envoi" in caplog.text


def test_smtp_mode_sends_the_message(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_message(self, message):
            sent.append((message["To"], message["Subject"], message.get_content().strip()))

    monkeypatch.setenv("MAIL_MODE", "smtp")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    assert mail.send_mail("vesper@exemple.fr", "Objet", "Texte")
    assert sent == [("localhost", 1025), ("vesper@exemple.fr", "Objet", "Texte")]


# --- Journaux sans adresse en clair, liens expirés effacés ---------------------------------------

def test_mask_email():
    assert mail.mask_email("zoe@exemple.fr") == "z***@exemple.fr"
    assert mail.mask_email("pas-une-adresse") == "***"


def test_failed_login_with_an_email_is_logged_masked(client, caplog):
    register(client)
    with caplog.at_level(logging.WARNING, logger="backend.server.auth"):
        login(client, "vesper@exemple.fr", "mauvais")
    assert "v***@exemple.fr" in caplog.text and "vesper@exemple.fr" not in caplog.text


def test_sent_email_is_logged_masked(monkeypatch, caplog):
    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_message(self, message):
            pass

    monkeypatch.setenv("MAIL_MODE", "smtp")
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    with caplog.at_level(logging.INFO, logger="backend.mail"):
        mail.send_mail("vesper@exemple.fr", "Objet", "Texte")
    assert "v***@exemple.fr" in caplog.text and "vesper@exemple.fr" not in caplog.text


def test_daily_purge_removes_stale_reset_links(client, outbox):
    from backend.db import PasswordResetToken
    from backend.server.account_removal import purge_inactive_accounts
    register(client)
    forgot(client)
    forgot(client)
    with get_session() as db:
        old, recent = db.query(PasswordResetToken).order_by(PasswordResetToken.id).all()
        old.expires_at = utcnow() - timedelta(days=2)  # expiré depuis plus d'un jour : effacé
        db.commit()
    purge_inactive_accounts()
    with get_session() as db:
        assert [t.id for t in db.query(PasswordResetToken)] == [recent.id]
