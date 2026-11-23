"""Adresse e-mail des comptes, mot de passe oublié et avertissement avant suppression (service, base en mémoire)."""
from datetime import timedelta

import pytest

from backend.accounts import service
from backend.accounts.service import AccountError
from backend.db import PasswordResetToken, User
from backend.db.models import utcnow


def account(db, pseudo="Vesper", email="vesper@exemple.fr", password="mot-de-passe"):
    return service.register(db, pseudo, password, email)


def refusal(call) -> AccountError:
    with pytest.raises(AccountError) as error:
        call()
    return error.value


# --- Inscription et connexion ---------------------------------------------------------------

def test_email_is_required_and_normalized(db):
    assert refusal(lambda: account(db, email="")).message == "Veuillez indiquer une adresse e-mail."
    user = account(db, email="  Vesper@Exemple.FR ")
    assert user.email == "vesper@exemple.fr"


@pytest.mark.parametrize("email", ["vesper", "vesper@", "@exemple.fr", "vesper@exemple", "ves per@exemple.fr",
                                   "a" * 250 + "@exemple.fr"])
def test_invalid_emails_are_refused(db, email):
    assert refusal(lambda: account(db, email=email)).message == "Adresse e-mail invalide."


def test_email_is_unique_whatever_the_case(db):
    account(db)
    error = refusal(lambda: account(db, "Ombre", "VESPER@exemple.fr"))
    assert (error.message, error.status) == ("Cette adresse e-mail est déjà utilisée par un autre compte.", 409)


def test_login_with_pseudo_or_email(db):
    user = account(db)
    assert service.authenticate(db, "Vesper", "mot-de-passe") is user
    assert service.authenticate(db, "VESPER@exemple.fr", "mot-de-passe") is user
    assert service.authenticate(db, "vesper@exemple.fr", "mauvais") is None
    assert service.authenticate(db, "inconnu@exemple.fr", "mot-de-passe") is None


def test_change_email(db):
    user = account(db)
    account(db, "Ombre", "ombre@exemple.fr")
    assert refusal(lambda: service.change_email(db, user, "mauvais", "nouveau@exemple.fr")).status == 403
    assert refusal(lambda: service.change_email(db, user, "mot-de-passe", "ombre@exemple.fr")).status == 409
    service.change_email(db, user, "mot-de-passe", "Nouveau@Exemple.fr")
    assert user.email == "nouveau@exemple.fr"


def test_admin_email_is_optional_and_added_later(db):
    admin = service.ensure_admin(db, "Gardien", "mot-de-passe-admin", "")
    assert admin.email is None
    service.ensure_admin(db, "Gardien", "mot-de-passe-admin", "gardien@exemple.fr")
    assert admin.email == "gardien@exemple.fr"


# --- Mot de passe oublié --------------------------------------------------------------------

def test_reset_token_is_stored_hashed(db):
    user = account(db)
    token = service.create_reset_token(db, user)
    entry = db.query(PasswordResetToken).one()
    assert token not in entry.token_hash and len(entry.token_hash) == 64


def test_reset_password_with_token_once(db):
    user = account(db)
    token = service.create_reset_token(db, user)
    service.reset_password_with_token(db, token, "nouveau-mdp")
    assert user.token_version == 1  # tous les appareils déconnectés
    assert service.authenticate(db, "Vesper", "nouveau-mdp") is user
    assert refusal(lambda: service.reset_password_with_token(db, token, "encore-un-mdp")).message == \
        service.INVALID_RESET_LINK


def test_reset_link_expires(db):
    user = account(db)
    token = service.create_reset_token(db, user)
    db.query(PasswordResetToken).one().expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert refusal(lambda: service.reset_password_with_token(db, token, "nouveau-mdp")).message == \
        service.INVALID_RESET_LINK


def test_only_the_last_reset_link_works(db):
    user = account(db)
    first = service.create_reset_token(db, user)
    second = service.create_reset_token(db, user)
    assert refusal(lambda: service.reset_password_with_token(db, first, "nouveau-mdp")).status == 400
    service.reset_password_with_token(db, second, "nouveau-mdp")


def test_too_short_password_keeps_the_link_usable(db):
    user = account(db)
    token = service.create_reset_token(db, user)
    assert "8 caractères" in refusal(lambda: service.reset_password_with_token(db, token, "court")).message
    service.reset_password_with_token(db, token, "assez-long")


def test_unknown_token_is_refused(db):
    assert refusal(lambda: service.reset_password_with_token(db, "inconnu", "nouveau-mdp")).status == 400


def test_delete_account_removes_email_and_reset_links(db):
    user = account(db)
    service.create_reset_token(db, user)
    service.delete_account(db, user)
    assert db.query(PasswordResetToken).count() == 0
    assert service.find_by_email(db, "vesper@exemple.fr") is None


# --- Avertissement avant suppression pour inactivité -------------------------------------------

def days_ago(days):
    return utcnow() - timedelta(days=days)


def test_accounts_to_warn_one_month_before_deletion(db):
    sleeper, recent = account(db), account(db, "Actif", "actif@exemple.fr")
    admin = service.ensure_admin(db, "Gardien", "mot-de-passe-admin", "gardien@exemple.fr")
    no_email = service.ensure_admin(db, "Autre", "mot-de-passe-admin", "")  # sans adresse
    no_email.is_admin = False
    for user in (sleeper, admin, no_email):
        user.last_seen_at = days_ago(340)
    recent.last_seen_at = days_ago(300)
    db.commit()
    assert service.accounts_to_warn(db) == [sleeper]

    service.mark_warned(db, sleeper)
    assert service.accounts_to_warn(db) == []  # une seule fois


def test_activity_cancels_the_warning(db):
    user = account(db)
    user.last_seen_at, user.inactivity_warned_at = days_ago(340), days_ago(5)
    db.commit()
    service.authenticate(db, "Vesper", "mot-de-passe")
    assert user.inactivity_warned_at is None


@pytest.mark.parametrize("warned_days_ago, deleted", [(None, False), (10, False), (31, True)])
def test_account_is_deleted_only_30_days_after_the_warning(db, warned_days_ago, deleted):
    user = account(db)
    user.last_seen_at = days_ago(400)
    user.inactivity_warned_at = days_ago(warned_days_ago) if warned_days_ago is not None else None
    db.commit()
    assert (service.delete_inactive_accounts(db) == ["Vesper"]) is deleted


def test_account_without_email_is_deleted_at_the_deadline(db):
    user = service.ensure_admin(db, "Ancien", "mot-de-passe", "")
    user.is_admin = False
    user.last_seen_at = days_ago(366)
    db.commit()
    assert service.delete_inactive_accounts(db) == ["Ancien"]
    assert db.query(User).count() == 0


def test_deletion_date_is_one_year_after_last_activity(db):
    user = account(db)
    assert service.deletion_date(user) - service._as_utc(user.last_seen_at) == timedelta(days=365)
