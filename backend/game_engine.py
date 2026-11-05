import random
from typing import Callable, NamedTuple, Optional

from backend.agent_factory import create_all_agents
from backend.memory_manager import MemoryManager, game_master
from backend.models import Alignement, EventType, GameState, Phase, Player, Role
from backend.prompt_loader import PromptLoader
from backend.rules import (
    assign_players,
    choose_false_lead,
    first_night_info,
    legal_actions,
    night_steps,
    random_legal_choice,
    resolve_night,
    resolve_vote,
    set_link,
    vote_result,
    winner,
)
from backend.rules.powers import FALSE_LEAD_KEY

# Fonction optionnelle qui renvoie le choix d'un joueur (ou () si elle n'en a pas).
ChoiceFn = Callable[[GameState, str], tuple[str, ...]]
# Fonction optionnelle qui renvoie la cible d'un vote (ou None pour s'abstenir).
VoteFn = Callable[[GameState, str], Optional[str]]


class TurnResult(NamedTuple):
    state: GameState
    night_choices: dict[str, tuple[str, ...]]
    votes: dict[str, Optional[str]]
    executed: Optional[str]
    night_deaths: tuple[str, ...]
    game_winner: Optional[Alignement]


def _info_text(state: GameState, info) -> str:
    subjects = ", ".join(state.player(pid).name for pid in info.subject_ids)
    if info.kind == "demon":
        return f"Première nuit : tu es le Diablotin. Tes alliés sont : {subjects}."
    if info.kind == "minion":
        return f"Première nuit : tu es l'Empoisonneur. Le Diablotin est : {subjects}."
    return f"Première nuit : parmi {subjects}, l'un d'eux est le Diablotin."


def setup_game(
    names: dict[str, str],
    human_id: str,
    personality_names: list[str],
    rng: random.Random,
    prompt_loader: Optional[PromptLoader] = None,
):
    """Met en place une partie : rôles, personnalités, fausse piste de la Voyante,
    agents IA et infos de première nuit. Renvoie (état, agents, mémoire)."""
    assignments = assign_players(names, human_id, personality_names, rng)

    players = tuple(
        Player(id=player_id, name=name, role=Role(**role_data))
        for player_id, (name, role_data, _) in assignments.items()
    )
    state = GameState(turn=1, phase=Phase.NUIT, players=players, channels=())

    roles = {player.id: player.role for player in players}
    false_lead = choose_false_lead(roles, rng)
    psychic = next(player for player in players if player.role.name_EN == "psychic")
    state = state.replace_player(set_link(psychic, FALSE_LEAD_KEY, false_lead))

    memory = MemoryManager(list(names))
    agents = create_all_agents(assignments, memory, human_id, prompt_loader)

    memory.set_moment(state.turn, state.phase)
    for info in first_night_info(state, rng):
        memory.add_event(
            EventType.role_info,
            game_master,
            _info_text(state, info),
            frozenset({info.viewer_id}),
        )

    return state, agents, memory


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
    Renvoie (état après la nuit, choix de nuit). Les choix servent aussi à la Voyante."""
    choices = collect_night_choices(state, rng, choose)
    return resolve_night(state, choices), choices


def collect_votes(state: GameState, choose: Optional[VoteFn] = None) -> dict[str, Optional[str]]:
    """Recueille les votes des joueurs qui peuvent voter.
    Une cible absente, morte ou inconnue devient une abstention."""
    alive = {player.id for player in state.players if player.alive}
    votes: dict[str, Optional[str]] = {}
    for player in state.players:
        if not player.can_vote:
            continue
        target = choose(state, player.id) if choose else None
        if target not in alive:
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


def _deaths(before: GameState, after: GameState) -> tuple[str, ...]:
    return tuple(
        player.id
        for player in before.players
        if player.alive and not after.player(player.id).alive
    )


def play_turn(
    state: GameState,
    rng: random.Random,
    night_choose: Optional[ChoiceFn] = None,
    vote_choose: Optional[VoteFn] = None,
) -> TurnResult:
    """Joue un tour complet : nuit, contrôle de victoire, jour, contrôle de victoire.
    Passe à la nuit suivante si la partie continue."""
    if state.phase != Phase.NUIT:
        raise ValueError("un tour commence par la nuit")

    after_night, night_choices = play_night(state, rng, night_choose)
    night_deaths = _deaths(state, after_night)
    if winner(after_night) is not None:
        return TurnResult(after_night, night_choices, {}, None, night_deaths, winner(after_night))

    # NUIT -> DISCUSSION -> VOTE
    day_state = after_night.next_phase().next_phase()
    after_day, votes, executed = play_day(day_state, vote_choose)
    game_winner = winner(after_day)
    if game_winner is None:
        # VOTE -> NUIT, tour suivant
        after_day = after_day.next_phase()
    return TurnResult(after_day, night_choices, votes, executed, night_deaths, game_winner)


def play_game(
    state: GameState,
    rng: random.Random,
    night_choose: Optional[ChoiceFn] = None,
    vote_choose: Optional[VoteFn] = None,
    max_turns: int = 20,
) -> GameState:
    """Joue des tours jusqu'à la victoire d'un camp. Renvoie l'état final."""
    for _ in range(max_turns):
        result = play_turn(state, rng, night_choose, vote_choose)
        state = result.state
        if result.game_winner is not None:
            return state
    raise RuntimeError(f"partie non terminée après {max_turns} tours")