"""Étapes d'un tour, utilisées par la boucle de jeu (engine/turn.py) : choix et résolution de la nuit,
vote, morts de la nuit, réponse du Médium, et annonces dans la mémoire des joueurs."""
import random
from typing import Callable, NamedTuple, Optional

from backend.ai.memory_manager import MemoryManager, game_master
from backend.models import Alignment, EventType, GameState, RoleKey
from backend.rules import (
    filter_valet_votes,
    legal_actions,
    night_steps,
    random_legal_choice,
    resolve_night,
    resolve_vote,
    vote_result,
    vote_targets,
)
from backend.rules.powers import medium_answer

# Fonction optionnelle qui renvoie le choix d'un joueur (ou () si elle n'en a pas).
ChoiceFn = Callable[[GameState, str], tuple[str, ...]]
# Fonction optionnelle qui renvoie la cible d'un vote (ou None pour s'abstenir).
VoteFn = Callable[[GameState, str], Optional[str]]


class Ballot(NamedTuple):
    """Bulletin d'un votant, tel que tout le monde le voit."""
    voter: str
    target: Optional[str]  # vote qui compte (None : personne)
    ghost: bool            # votant déjà mort qui a voté : il utilise sa voix d'outre-tombe


class TurnResult(NamedTuple):
    state: GameState
    night_choices: dict[str, tuple[str, ...]]
    votes: dict[str, Optional[str]]
    executed: Optional[str]
    night_deaths: tuple[str, ...]
    game_winner: Optional[Alignment]
    # Agents dont l'IA n'a pas répondu au vote : leur abstention est signalée sur le bulletin
    vote_failures: frozenset[str] = frozenset()
    # Bulletins du vote (vote_ballots) : seule source de la mention outre-tombe
    ballots: tuple[Ballot, ...] = ()


def _is_valid_choice(state: GameState, player_id: str, choice: tuple[str, ...]) -> bool:
    legal = legal_actions(state, player_id)
    return len(choice) == legal.count and all(target in legal.targets for target in choice)


def collect_night_choices(
    state: GameState,
    rng: random.Random,
    choose: Optional[ChoiceFn] = None,
) -> dict[str, tuple[str, ...]]:
    """Recueille les choix de nuit dans l'ordre de jeu.
    night_steps renvoie (id du joueur, choix nécessaire). Un choix invalide ou absent
    est remplacé par un choix aléatoire légal."""
    choices: dict[str, tuple[str, ...]] = {}
    for player_id, needs_choice in night_steps(state):
        if not needs_choice:
            continue
        picked = choose(state, player_id) if choose else ()
        if not _is_valid_choice(state, player_id, picked):
            picked = random_legal_choice(state, player_id, rng)
        choices[player_id] = picked
    return choices


def play_night(
    state: GameState,
    rng: random.Random,
    choose: Optional[ChoiceFn] = None,
) -> tuple[GameState, dict[str, tuple[str, ...]]]:
    """Joue la nuit : recueille les choix, puis les résout.
    Renvoie (état après la nuit, choix de nuit). Les choix servent aussi au Médium."""
    choices = collect_night_choices(state, rng, choose)
    return resolve_night(state, choices), choices


def collect_votes(state: GameState, choose: Optional[VoteFn] = None) -> dict[str, Optional[str]]:
    """Recueille les votes des joueurs qui peuvent voter.
    Une cible non permise (morte, inconnue, ou le votant lui-même) devient une abstention."""
    votes: dict[str, Optional[str]] = {}
    for player in state.players:
        if not player.can_vote:
            continue
        target = choose(state, player.id) if choose else None
        if target not in vote_targets(state, player.id):
            target = None
        votes[player.id] = target
    return votes


def play_day(
    state: GameState,
    choose: Optional[VoteFn] = None,
) -> tuple[GameState, dict[str, Optional[str]], Optional[str]]:
    """Joue le vote du jour. Renvoie (état après le vote, votes, joueur exécuté ou None)."""
    votes = collect_votes(state, choose)
    executed = vote_result(state, votes)
    return resolve_vote(state, votes), votes, executed


def deaths_between(before: GameState, after: GameState) -> tuple[str, ...]:
    """Joueurs vivants dans `before` et morts dans `after` (ex. les morts de la nuit)."""
    return tuple(
        player.id
        for player in before.players
        if player.alive and not after.player(player.id).alive
    )


def reveal_medium_answer(
    state: GameState,
    choices: dict[str, tuple[str, ...]],
    memory: MemoryManager,
    rng: random.Random,
) -> None:
    """Écrit dans la mémoire du Médium le résultat de son sondage de la nuit.
    À appeler après la résolution de la nuit (state = état après la nuit), avant la discussion.
    Un Médium mort pendant la nuit ne reçoit aucune information."""
    for player in state.players:
        if player.role.name_EN != RoleKey.MEDIUM or player.id not in choices or not player.alive:
            continue
        probed = choices[player.id]
        found = medium_answer(state, player.id, probed, rng)
        names = " et ".join(state.player(pid).name for pid in probed)
        verdict = "au moins un est un démon" if found else "aucun n'est un démon"
        memory.add_event(
            EventType.ROLE_INFO,
            game_master,
            f"Parmi {names}, {verdict}.",
            frozenset({player.id}),
        )


def record_night_choices(state: GameState, choices: dict[str, tuple[str, ...]], memory: MemoryManager) -> None:
    """Chaque joueur qui a agi garde une trace privée de sa cible. Un joueur mort pendant la nuit n'en garde pas."""
    for player_id, target_ids in choices.items():
        if not target_ids or not state.player(player_id).alive:
            continue
        names = " et ".join(state.player(pid).name for pid in target_ids)
        memory.add_event(EventType.NIGHT_ACTION, game_master,
                         f"Nuit {state.turn} : tu as choisi {names}.", frozenset({player_id}))

def record_night_deaths(state: GameState, deaths: tuple[str, ...], memory: MemoryManager) -> None:
    """Annonce publique des morts de la nuit, au réveil du village : tout le monde sait qui est mort
    (pas comment). À appeler avec l'état après la nuit, au moment de la nuit qui vient de finir."""
    if not deaths:
        memory.add_public(EventType.DEATH, game_master, "Personne n'est mort cette nuit.")
    for player_id in deaths:
        memory.add_public(EventType.DEATH, game_master, f"{state.player(player_id).name} est mort·e cette nuit.")


def vote_ballots(state: GameState, votes: dict[str, Optional[str]]) -> tuple[Ballot, ...]:
    """Bulletins du vote, à partir des votes qui comptent (règle du Valet appliquée par sécurité :
    le moteur ne demande au Valet de voter que si son maître a voté, il n'y a donc rien à annuler).
    state = état au moment du vote, avant l'exécution. Une abstention n'utilise pas la voix d'outre-tombe."""
    counted = filter_valet_votes(state, votes)
    return tuple(
        Ballot(voter_id, target_id, ghost=target_id is not None and not state.player(voter_id).alive)
        for voter_id, target_id in counted.items()
    )


def record_vote(state: GameState, votes: dict[str, Optional[str]], executed: Optional[str],
                memory: MemoryManager) -> None:
    """Annonce publique du vote : le bulletin de chaque votant, puis l'exécution.
    state = état au moment du vote (avant l'exécution)."""
    if votes:
        lines = []
        for ballot in vote_ballots(state, votes):
            target = state.player(ballot.target).name if ballot.target else "personne"
            mention = " (voix d'outre-tombe)" if ballot.ghost else ""
            lines.append(f"{state.player(ballot.voter).name} → {target}{mention}")
        memory.add_public(EventType.VOTE, game_master, f"Votes : {', '.join(lines)}.")
    else:
        memory.add_public(EventType.VOTE, game_master, "Personne n'a pu voter.")
    if executed is None:
        memory.add_public(EventType.DEATH, game_master, "Personne n'est exécuté aujourd'hui.")
    else:
        memory.add_public(EventType.DEATH, game_master, f"{state.player(executed).name} est exécuté·e par le village.")
