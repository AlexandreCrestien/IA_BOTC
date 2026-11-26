"""Succès : définitions, faits relevés pendant la partie, et succès obtenus à la fin d'une partie.

Les succès sont calculés à la fin d'une partie terminée normalement (victoire ou défaite) ;
une partie abandonnée ou interrompue n'en débloque aucun. Les textes sont affichés au joueur (français).
Un succès caché (hidden) apparaît sous la forme « ??? » tant qu'il n'est pas débloqué.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from backend.models import RoleKey


@dataclass
class GameFacts:
    """Ce que le joueur humain a fait ou subi pendant la partie (relevé tour par tour par game_runner)."""
    ghost_vote_used: bool = False             # il a voté depuis l'au-delà
    voted_for_executed: bool = False          # il a voté pour un joueur qui a été exécuté
    executed_turn: Optional[int] = None       # tour de son exécution
    killed_at_night: bool = False             # tué la nuit (seul le Faucheur tue la nuit)

    def record_turn(self, human_id: str, turn: int, result) -> None:
        """result : TurnResult du moteur (bulletins, exécuté, morts de la nuit)."""
        if human_id in result.night_deaths:
            self.killed_at_night = True
        for ballot in result.ballots:
            if ballot.voter != human_id:
                continue
            if ballot.ghost:
                self.ghost_vote_used = True
            if ballot.target is not None and ballot.target == result.executed:
                self.voted_for_executed = True
        if result.executed == human_id:
            self.executed_turn = turn


@dataclass(frozen=True)
class GameSummary:
    """Fin de partie du joueur humain, telle que vue par les succès."""
    role: RoleKey
    won: bool
    turns: int
    facts: GameFacts = field(default_factory=GameFacts)


@dataclass(frozen=True)
class Achievement:
    code: str            # identifiant stocké en base (ne jamais le renommer)
    title: str
    description: str
    hidden: bool
    message: Optional[str]  # petit mot affiché au déblocage
    earned: Callable[[GameSummary], bool]


def _win_as(role: RoleKey) -> Callable[[GameSummary], bool]:
    return lambda game: game.won and game.role == role


ROLE_TITLES = {
    RoleKey.REAPER: ("Faucheur", "La moisson a été bonne."),
    RoleKey.APOTHECARY: ("Apothicaire", "Une goutte de trop, au bon endroit."),
    RoleKey.WATCHMAN: ("Veilleur", "Les nuits sont moins longues quand on veille."),
    RoleKey.MEDIUM: ("Médium", "Les esprits avaient raison."),
    RoleKey.INQUISITOR: ("Inquisiteur", "Rien n'échappe à la question."),
    RoleKey.VALET: ("Valet", "Bien servi, bien gagné."),
}

ACHIEVEMENTS: tuple[Achievement, ...] = (
    *(
        Achievement(f"win_{role.value}", f"Victoire : {name}", f"Gagner une partie en tant que {name}.",
                    hidden=False, message=message, earned=_win_as(role))
        for role, (name, message) in ROLE_TITLES.items()
    ),
    Achievement("ghost_vote", "Voix d'outre-tombe", "Utiliser sa voix d'outre-tombe.",
                hidden=False, message="Même mort, on a son mot à dire.",
                earned=lambda game: game.facts.ghost_vote_used),
    Achievement("executioner", "Bourreau", "Voter pour un joueur qui est exécuté.",
                hidden=False, message="La corde a parlé.",
                earned=lambda game: game.facts.voted_for_executed),
    Achievement("executed", "Sur l'échafaud", "Être exécuté.",
                hidden=False, message="Le village a tranché… vous.",
                earned=lambda game: game.facts.executed_turn is not None),
    Achievement("quick_win", "Expéditif", "Gagner une partie en 3 tours ou moins.",
                hidden=False, message="Rapide et sans bavure.",
                earned=lambda game: game.won and game.turns <= 3),
    Achievement("one_turn_win", "Coup de maître", "Gagner une partie en un seul tour.",
                hidden=True, message="Talents de détective surnaturels ou chance inouïe ?",
                earned=lambda game: game.won and game.turns == 1),
    Achievement("executed_first_turn", "Premier sacrifié", "Être exécuté au premier tour.",
                hidden=True, message="Le village ne vous a même pas laissé le temps de vous présenter.",
                earned=lambda game: game.facts.executed_turn == 1),
    Achievement("win_after_execution", "Revenant", "Gagner une partie en ayant été exécuté.",
                hidden=True, message="La corde n'aura pas suffi.",
                earned=lambda game: game.won and game.facts.executed_turn is not None),
    Achievement("win_after_reaper", "Increvable", "Gagner une partie en ayant été victime du Faucheur.",
                hidden=True, message="Mort, mais pas vaincu.",
                earned=lambda game: game.won and game.facts.killed_at_night),
)

BY_CODE = {achievement.code: achievement for achievement in ACHIEVEMENTS}


def earned_achievements(game: GameSummary) -> list[Achievement]:
    """Succès obtenus par cette partie (déjà débloqués ou non), dans l'ordre de la liste."""
    return [achievement for achievement in ACHIEVEMENTS if achievement.earned(game)]
