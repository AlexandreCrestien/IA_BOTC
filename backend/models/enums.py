from enum import Enum, StrEnum


class RoleKey(StrEnum):
    """Identifiant d'un rôle : clé du catalogue et nom du fichier skills/roles/<clé>.md.
    StrEnum : vaut sa chaîne ("imp"…), mais une faute de frappe est une erreur immédiate."""
    IMP = "imp"
    POISONER = "poisoner"
    MONK = "monk"
    PSYCHIC = "psychic"
    DETECTIVE = "detective"
    BUTLER = "butler"


class Phase(str, Enum):
    NIGHT = "nuit"
    DISCUSSION = "discussion"
    VOTE = "vote"


class Team(str, Enum):
    TOWNSFOLK = "villageois"
    OUTSIDER = "outsider"
    MINION = "sbire"
    DEMON = "demon"


class Alignment(str, Enum):
    GOOD = "villageois"
    EVIL = "demon"


class EffectType(str, Enum):
    PROTECTED = "protege"
    POISONED = "empoisonne"

class EventType(str, Enum):
    DEATH = "death"
    PUBLIC_MESSAGE = "public_message"
    PRIVATE_MEETING = "private_meeting"
    PRIVATE_SUMMARY = "private_summary"
    VOTE = "vote"
    NIGHT_ACTION = "night_action"
    ROLE_INFO = "role_info"