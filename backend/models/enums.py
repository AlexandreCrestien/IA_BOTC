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