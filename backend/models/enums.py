from enum import Enum


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
    SONDE = "sonde"
    TUE = "tue"

class EventType(str, Enum):
    announcement = "announcement"
    death = "death"
    public_message = "public_message"
    private_meeting = "private_meeting"
    private_summary = "private_summary"
    nomination = "nomination"
    vote = "vote"
    night_action = "night_action"
    night_info = "night_info"
    role_info = "role_info"