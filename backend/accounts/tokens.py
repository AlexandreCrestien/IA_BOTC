"""Jetons de connexion (JWT), transportés dans un cookie HttpOnly.

Le jeton contient l'identifiant du compte et sa version de jeton (token_version) : incrémenter
la version (changement ou réinitialisation du mot de passe) invalide tous les jetons déjà émis.
"""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional

import jwt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

COOKIE_NAME = "lh_session"
TOKEN_LIFETIME = timedelta(days=7)
ALGORITHM = "HS256"

_fallback_secret: Optional[str] = None


def _secret() -> str:
    """JWT_SECRET (.env). À défaut, une clé aléatoire : les connexions ne survivent pas au redémarrage."""
    global _fallback_secret
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret
    if _fallback_secret is None:
        _fallback_secret = secrets.token_hex(32)
        logger.warning("JWT_SECRET absent du .env : clé temporaire, les joueurs seront déconnectés au redémarrage.")
    return _fallback_secret


class TokenClaims(NamedTuple):
    user_id: int
    version: int


def create_token(user_id: int, version: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "ver": version, "iat": now, "exp": now + TOKEN_LIFETIME}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def read_token(token: str) -> Optional[TokenClaims]:
    """Contenu d'un jeton valide (signature, expiration), ou None."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["sub", "ver", "exp"]})
        return TokenClaims(int(payload["sub"]), int(payload["ver"]))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None
