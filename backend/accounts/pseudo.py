"""Règles du pseudo, communes aux comptes et aux invités."""
import re
import unicodedata

from backend.engine.config import AI_NAMES

# Lettres (accents compris), chiffres, - _ ' ’ ; 20 caractères au plus.
# Même règle côté front (static/js/connection.js, PSEUDO_PATTERN).
PSEUDO_PATTERN = re.compile(r"[\w'’-]{1,20}")

# Pseudos réservés : « Codex » signe les annonces du chat (backend/server/protocol.py)
RESERVED = {"game_master", "codex"}

INVALID_PSEUDO = ("Pseudo invalide : 1 à 20 caractères parmi lettres, chiffres, tirets, « _ » et apostrophes, "
                  "et différent du nom d'un personnage.")


def normalize_pseudo(pseudo: str) -> str:
    """NFC : un « é » saisi en deux caractères (e + accent) devient un seul, comme côté front."""
    return unicodedata.normalize("NFC", pseudo.strip())


def is_reserved(pseudo: str) -> bool:
    """Pseudo réservé, ou nom (ou identifiant) d'un agent, sans tenir compte de la casse."""
    taken = {k.casefold() for k in AI_NAMES} | {v.casefold() for v in AI_NAMES.values()} | RESERVED
    return pseudo.casefold() in taken


def pseudo_is_valid(pseudo: str) -> bool:
    return PSEUDO_PATTERN.fullmatch(pseudo) is not None and not is_reserved(pseudo)
