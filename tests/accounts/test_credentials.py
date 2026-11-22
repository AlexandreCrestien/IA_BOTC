"""Règles du pseudo et du mot de passe, hachage bcrypt et jetons JWT."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend.accounts import tokens
from backend.accounts.passwords import hash_password, password_error, verify_password
from backend.accounts.pseudo import normalize_pseudo, pseudo_is_valid
from backend.accounts.tokens import create_token, read_token


@pytest.mark.parametrize("pseudo", ["Vesper", "élise", "Jean-Luc", "o'neil", "d’Arc", "joueur_42", "a" * 20])
def test_valid_pseudos(pseudo):
    assert pseudo_is_valid(pseudo)


@pytest.mark.parametrize("pseudo", ["", "a" * 21, "avec espace", "point.", "dièse#", "codex", "CODEX", "game_master",
                                    "p1", "Lord Ashcombe"])
def test_invalid_or_reserved_pseudos(pseudo):
    assert not pseudo_is_valid(pseudo)


def test_pseudo_is_normalized():
    assert normalize_pseudo("  élise ") == "élise"


def test_password_rules():
    assert password_error("court") == "Le mot de passe doit contenir au moins 8 caractères."
    assert password_error("assez-long") is None
    assert password_error("a" * 72) is None
    assert "trop long" in password_error("a" * 73)
    assert "trop long" in password_error("é" * 37)  # 74 octets


def test_password_is_hashed_and_verified():
    hashed = hash_password("mot-de-passe")
    assert hashed != "mot-de-passe" and hashed.startswith("$2")
    assert verify_password("mot-de-passe", hashed)
    assert not verify_password("autre-chose", hashed)
    assert not verify_password("mot-de-passe", "hash-illisible")


def test_token_round_trip():
    claims = read_token(create_token(7, 3))
    assert claims == (7, 3)


def test_tampered_or_foreign_token_is_refused():
    token = create_token(7, 0)
    assert read_token(token[:-2] + "xx") is None
    assert read_token(jwt.encode({"sub": "7", "ver": 0, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                                 "une-autre-cle-de-signature-assez-longue", algorithm="HS256")) is None
    assert read_token("n'importe quoi") is None


def test_expired_token_is_refused():
    expired = jwt.encode({"sub": "7", "ver": 0, "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
                         tokens._secret(), algorithm="HS256")
    assert read_token(expired) is None


def test_token_without_version_is_refused():
    token = jwt.encode({"sub": "7", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                       tokens._secret(), algorithm="HS256")
    assert read_token(token) is None


def test_missing_secret_falls_back_to_a_temporary_key(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    monkeypatch.setattr(tokens, "_fallback_secret", None)
    token = create_token(1, 0)
    assert read_token(token) == (1, 0)
    assert tokens._fallback_secret is not None
