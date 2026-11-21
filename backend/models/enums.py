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
    NUIT = "nuit"
    DISCUSSION = "discussion"
    VOTE = "vote"


class Equipe(str, Enum):
    VILLAGEOIS = "villageois"
    OUTSIDER = "outsider"
    SBIRE = "sbire"
    DEMON = "demon"


class Alignement(str, Enum):
    BON = "villageois"
    MAUVAIS = "demon"


class TypeEffet(str, Enum):
    PROTEGE = "protege"
    EMPOISONNE = "empoisonne"

class EventType(str, Enum):
    death = "death"
    public_message = "public_message"
    private_meeting = "private_meeting"
    private_summary = "private_summary"
    vote = "vote"
    night_action = "night_action"
    role_info = "role_info"