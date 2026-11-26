"""Vérification de l'adresse e-mail (service, base en mémoire)."""
from datetime import timedelta

import pytest

from backend.accounts import service
from backend.accounts.service import AccountError
from backend.db import EmailVerificationToken, User
from backend.db.models import utcnow


def account(db, pseudo="Vesper", email="vesper@exemple.fr"):
    return service.register(db, pseudo, "mot-de-passe", email)


def refusal(call) -> AccountError:
    with pytest.raises(AccountError) as error:
        call()
    return error.value


def test_new_account_is_not_verified(db):
    user = account(db)
    assert not user.email_verified


def test_admin_email_from_env_is_trusted(db):
    admin = service.ensure_admin(db, "Gardien", "mot-de-passe-admin", "gardien@exemple.fr")
    assert admin.email_verified


def test_verification_link_works_once(db):
    user = account(db)
    token = service.create_verification_token(db, user)
    entry = db.query(EmailVerificationToken).one()
    assert token not in entry.token_hash  # seule l'empreinte est stockée
    assert service.verify_email(db, token) == (user, None) and user.email_verified
    assert refusal(lambda: service.verify_email(db, token)).message == service.INVALID_VERIFY_LINK


def test_verification_link_expires_after_24_hours(db):
    user = account(db)
    token = service.create_verification_token(db, user)
    entry = db.query(EmailVerificationToken).one()
    assert entry.expires_at - entry.created_at == timedelta(hours=24)
    entry.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert refusal(lambda: service.verify_email(db, token)).status == 400


def test_only_the_last_link_works(db):
    user = account(db)
    first = service.create_verification_token(db, user)
    second = service.create_verification_token(db, user)
    assert refusal(lambda: service.verify_email(db, first)).status == 400
    service.verify_email(db, second)


def test_unverified_address_is_corrected_immediately(db):
    """Faute de frappe à l'inscription : la nouvelle adresse remplace l'ancienne tout de suite (toujours à vérifier)."""
    user = account(db, email="vespre@exemple.fr")
    token = service.change_email(db, user, "mot-de-passe", "vesper@exemple.fr")
    assert user.email == "vesper@exemple.fr" and not user.email_verified
    assert service.verification_target(db, user) == "vesper@exemple.fr"
    service.verify_email(db, token)
    assert user.email_verified


def test_verified_address_stays_until_the_new_one_is_confirmed(db):
    user = account(db)
    service.verify_email(db, service.create_verification_token(db, user))
    assert refusal(lambda: service.change_email(db, user, "mot-de-passe", "VESPER@exemple.fr")).message == \
        service.SAME_EMAIL
    token = service.change_email(db, user, "mot-de-passe", "nouveau@exemple.fr")
    assert (user.email, service.pending_email(db, user)) == ("vesper@exemple.fr", "nouveau@exemple.fr")
    assert service.authenticate(db, "vesper@exemple.fr", "mot-de-passe") is user  # l'ancienne marche encore
    service.verify_email(db, token)
    assert user.email == "nouveau@exemple.fr"


def test_address_taken_in_the_meantime_is_refused(db):
    user = account(db)
    service.verify_email(db, service.create_verification_token(db, user))
    token = service.change_email(db, user, "mot-de-passe", "libre@exemple.fr")
    account(db, "Ombre", "libre@exemple.fr")  # un autre compte prend l'adresse entre-temps
    assert refusal(lambda: service.verify_email(db, token)).status == 409
    assert user.email == "vesper@exemple.fr"


def test_already_verified_has_no_target(db):
    user = account(db)
    service.verify_email(db, service.create_verification_token(db, user))
    assert service.verification_target(db, user) is None


# --- Comptes jamais vérifiés ------------------------------------------------------------------

@pytest.mark.parametrize("hours, deleted", [(71, False), (73, True)])
def test_unverified_account_is_deleted_after_72_hours(db, hours, deleted):
    user = account(db)
    user.created_at = utcnow() - timedelta(hours=hours)
    db.commit()
    assert (service.delete_unverified_accounts(db) == ["Vesper"]) is deleted


def test_verified_admin_and_playing_accounts_are_kept(db):
    old = utcnow() - timedelta(days=10)
    verified, playing = account(db), account(db, "Joueur", "joueur@exemple.fr")
    service.verify_email(db, service.create_verification_token(db, verified))
    admin = service.ensure_admin(db, "Gardien", "mot-de-passe-admin", "")  # admin sans adresse
    for user in (verified, playing, admin):
        user.created_at = old
    db.commit()
    assert service.delete_unverified_accounts(db, keep=[playing.id]) == []
    assert db.query(User).count() == 3


def test_unverified_accounts_are_never_warned_by_email(db):
    user = account(db)
    user.last_seen_at = utcnow() - timedelta(days=340)
    db.commit()
    assert service.accounts_to_warn(db) == []


def test_verification_links_are_deleted_with_the_account_and_when_stale(db):
    user, other = account(db), account(db, "Ombre", "ombre@exemple.fr")
    service.create_verification_token(db, user)
    service.create_verification_token(db, other)
    db.query(EmailVerificationToken).filter_by(user_id=other.id).one().expires_at = utcnow() - timedelta(days=2)
    db.commit()
    service.delete_stale_reset_tokens(db)
    assert [t.user_id for t in db.query(EmailVerificationToken)] == [user.id]
    service.delete_account(db, user)
    assert db.query(EmailVerificationToken).count() == 0
