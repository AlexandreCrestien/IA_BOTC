"""Mots de passe : règles, hachage bcrypt et vérification. Le mot de passe n'est jamais stocké en clair."""
import os
from functools import cache
from typing import Optional

import bcrypt

MIN_LENGTH = 8
MAX_BYTES = 72  # bcrypt ne prend en compte que les 72 premiers octets : au-delà, on refuse


def password_error(password: str) -> Optional[str]:
    """Motif de refus du mot de passe, ou None s'il est accepté."""
    if len(password) < MIN_LENGTH:
        return f"Le mot de passe doit contenir au moins {MIN_LENGTH} caractères."
    if len(password.encode()) > MAX_BYTES:
        return f"Le mot de passe est trop long ({MAX_BYTES} octets au plus, les lettres accentuées en comptent deux)."
    return None


def _rounds() -> int:
    """Coût du hachage (2^rounds itérations). 12 par défaut ; les tests le baissent (BCRYPT_ROUNDS)."""
    return int(os.getenv("BCRYPT_ROUNDS", "12"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_rounds())).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # mot de passe trop long ou hash illisible
        return False


@cache
def _dummy_hash() -> str:
    return hash_password("mot-de-passe-factice")


def spend_verification_time(password: str) -> None:
    """Pseudo inconnu : on vérifie quand même un mot de passe, pour que le temps de réponse
    ne révèle pas si le compte existe."""
    verify_password(password, _dummy_hash())
