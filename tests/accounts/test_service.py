"""Opérations sur les comptes, directement sur une base en mémoire."""
import pytest

from backend.accounts import service
from backend.accounts.pseudo import INVALID_PSEUDO
from backend.accounts.service import AccountError
from backend.accounts.tokens import create_token
from backend.db import User


def account(db, pseudo="Vesper", password="mot-de-passe"):
    return service.register(db, pseudo, password)


def refusal(call) -> AccountError:
    with pytest.raises(AccountError) as error:
        call()
    return error.value


def test_register_hashes_the_password(db):
    user = account(db)
    assert user.id is not None and user.pseudo == "Vesper" and not user.is_admin
    assert user.password_hash != "mot-de-passe"


def test_register_refuses_taken_pseudo_whatever_the_case(db):
    account(db, "Vesper")
    error = refusal(lambda: account(db, "vesper"))
    assert (error.message, error.status) == ("Ce pseudo est déjà pris.", 409)


def test_register_refuses_invalid_pseudo_and_short_password(db):
    assert refusal(lambda: account(db, "Codex")).message == INVALID_PSEUDO
    assert refusal(lambda: account(db, "a b")).message == INVALID_PSEUDO
    assert "8 caractères" in refusal(lambda: account(db, "Vesper", "court")).message
    assert db.query(User).count() == 0


def test_authenticate(db):
    account(db)
    assert service.authenticate(db, "Vesper", "mot-de-passe").pseudo == "Vesper"
    assert service.authenticate(db, "VESPER", "mot-de-passe") is not None  # pseudo sans tenir compte de la casse
    assert service.authenticate(db, "Vesper", "mauvais") is None
    assert service.authenticate(db, "Inconnu", "mot-de-passe") is None


def test_user_from_token_checks_the_version(db):
    user = account(db)
    token = create_token(user.id, user.token_version)
    assert service.user_from_token(db, token) is user
    user.token_version += 1
    assert service.user_from_token(db, token) is None
    assert service.user_from_token(db, create_token(999, 0)) is None


def test_change_pseudo(db):
    user = account(db)
    account(db, "Ombre")
    assert refusal(lambda: service.change_pseudo(db, user, "mauvais", "Lune")).status == 403
    assert refusal(lambda: service.change_pseudo(db, user, "mot-de-passe", "ombre")).status == 409
    service.change_pseudo(db, user, "mot-de-passe", "Lune")
    assert user.pseudo == "Lune"
    service.change_pseudo(db, user, "mot-de-passe", "LUNE")  # même compte : changement de casse autorisé
    assert user.pseudo == "LUNE"


def test_change_password_invalidates_tokens(db):
    user = account(db)
    assert refusal(lambda: service.change_password(db, user, "mauvais", "nouveau-mdp")).message == \
        "Mot de passe actuel incorrect."
    assert "8 caractères" in refusal(lambda: service.change_password(db, user, "mot-de-passe", "court")).message
    service.change_password(db, user, "mot-de-passe", "nouveau-mdp")
    assert user.token_version == 1
    assert service.authenticate(db, "Vesper", "nouveau-mdp") is user


def test_reset_password(db):
    user = account(db)
    temporary = service.reset_password(db, user)
    assert user.token_version == 1
    assert service.authenticate(db, "Vesper", temporary) is user
    assert service.authenticate(db, "Vesper", "mot-de-passe") is None


def test_ensure_admin_creates_the_account_once(db):
    admin = service.ensure_admin(db, "Gardien", "mot-de-passe-admin")
    assert admin.is_admin
    assert service.ensure_admin(db, "Gardien", "autre-mot-de-passe") is admin  # mot de passe inchangé
    assert service.authenticate(db, "Gardien", "mot-de-passe-admin") is admin
    assert refusal(lambda: service.reset_password(db, admin)).status == 400


def test_ensure_admin_without_configuration(db):
    assert service.ensure_admin(db, "", "") is None  # variables vides (tests) : pas d'admin
    assert service.ensure_admin(db, "Gardien", "court") is None
    assert db.query(User).count() == 0


def test_ensure_admin_never_promotes_a_player(db):
    account(db, "Gardien")
    assert service.ensure_admin(db, "Gardien", "mot-de-passe-admin") is None
    assert not service.find_by_pseudo(db, "Gardien").is_admin


def test_ensure_admin_reads_the_environment(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PSEUDO", "Gardien")
    monkeypatch.setenv("ADMIN_PASSWORD", "mot-de-passe-admin")
    assert service.ensure_admin(db).pseudo == "Gardien"


def test_delete_account_keeps_anonymous_games(db):
    """Compte et succès supprimés ; parties détachées du compte, datées au jour près, gardées pour les statistiques."""
    from datetime import datetime, timezone
    from backend.db import GameRecord, UnlockedAchievement
    from backend.models import Alignment, RoleKey
    user, other = account(db, "Vesper"), account(db, "Ombre")
    played = datetime(2026, 11, 21, 20, 47, 13, tzinfo=timezone.utc)
    for owner in (user, other):
        db.add_all([GameRecord(user=owner, role=RoleKey.VALET, alignment=Alignment.GOOD, started_at=played,
                               ended_at=played, turns=4),
                    UnlockedAchievement(user=owner, code="win_valet")])
    db.commit()

    service.delete_account(db, user)
    assert service.find_by_pseudo(db, "Vesper") is None
    assert {a.user_id for a in db.query(UnlockedAchievement)} == {other.id}
    anonymous = db.query(GameRecord).filter(GameRecord.user_id.is_(None)).one()
    assert (anonymous.role, anonymous.turns, anonymous.ended_at) == (RoleKey.VALET, 4, None)
    assert anonymous.started_at.replace(tzinfo=None) == datetime(2026, 11, 21)  # jour seulement, sans l'heure
    assert db.query(GameRecord).filter(GameRecord.user_id == other.id).one().started_at.hour == 20  # intacte
    assert account(db, "Vesper").id is not None  # le pseudo est de nouveau libre


def test_admin_account_cannot_be_deleted(db):
    admin = service.ensure_admin(db, "Gardien", "mot-de-passe-admin")
    assert refusal(lambda: service.delete_account(db, admin)).status == 400
    assert service.find_by_pseudo(db, "Gardien") is admin



# --- Activité et comptes inactifs ------------------------------------------------------------

def test_activity_is_recorded_at_login_and_at_most_daily(db):
    from datetime import timedelta
    from backend.db.models import utcnow
    user = account(db)
    long_ago = utcnow() - timedelta(days=30)
    user.last_seen_at = long_ago
    db.commit()
    service.authenticate(db, "Vesper", "mot-de-passe")
    assert user.last_seen_at > long_ago                       # connexion : toujours notée

    recent = utcnow() - timedelta(hours=2)
    user.last_seen_at = recent
    db.commit()
    service.user_from_token(db, create_token(user.id, user.token_version))
    assert user.last_seen_at == recent                        # visite dans la journée : pas de nouvelle écriture
    user.last_seen_at = utcnow() - timedelta(days=2)
    db.commit()
    service.user_from_token(db, create_token(user.id, user.token_version))
    assert utcnow() - service._as_utc(user.last_seen_at) < timedelta(minutes=1)


def test_inactive_accounts_are_deleted_after_a_year(db):
    from datetime import timedelta
    from backend.db.models import utcnow
    admin = service.ensure_admin(db, "Gardien", "mot-de-passe-admin")
    sleeper, playing, active = account(db, "Dormeur"), account(db, "Joueur"), account(db, "Actif")
    for user in (admin, sleeper, playing):
        user.last_seen_at = utcnow() - timedelta(days=400)
    active.last_seen_at = utcnow() - timedelta(days=364)
    db.commit()

    deleted = service.delete_inactive_accounts(db, keep=[playing.id])
    assert deleted == ["Dormeur"]
    remaining = {u.pseudo for u in db.query(User)}
    assert remaining == {"Gardien", "Joueur", "Actif"}  # admin jamais supprimé ; partie en cours épargnée
