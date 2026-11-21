from enum import Enum, StrEnum


class RoleKey(StrEnum):
    """Identifiant d'un rôle : clé du catalogue et nom du fichier skills/roles/<clé>.md.
    StrEnum : vaut sa chaîne ("reaper"…), mais une faute de frappe est une erreur immédiate."""
    REAPER = "reaper"          # Faucheur
    APOTHECARY = "apothecary"  # Apothicaire
    WATCHMAN = "watchman"      # Veilleur
    MEDIUM = "medium"          # Médium
    INQUISITOR = "inquisitor"  # Inquisiteur
    VALET = "valet"            # Valet


class Phase(str, Enum):
    NIGHT = "nuit"
    DISCUSSION = "discussion"
    VOTE = "vote"


class Team(str, Enum):
    TOWNSFOLK = "townsfolk"    # Villageois
    OUTCAST = "outcast"        # Paria
    ACCOMPLICE = "accomplice"  # Complice
    DEMON = "demon"            # Démon


class Alignment(str, Enum):
    GOOD = "good"
    EVIL = "evil"


class EffectType(str, Enum):
    PROTECTED = "protected"
    POISONED = "poisoned"

class EventType(str, Enum):
    DEATH = "death"
    PUBLIC_MESSAGE = "public_message"
    PRIVATE_MEETING = "private_meeting"
    PRIVATE_SUMMARY = "private_summary"
    VOTE = "vote"
    NIGHT_ACTION = "night_action"
    ROLE_INFO = "role_info"