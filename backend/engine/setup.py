"""Mise en place d'une partie : rôles, personnalités, fausse piste du Médium, mémoire, agents IA
et informations de la première nuit."""
import random
from typing import Optional

from backend.ai.agent import create_all_agents
from backend.ai.memory_manager import MemoryManager, game_master
from backend.ai.prompt_loader import PromptLoader
from backend.models import EventType, GameState, Phase, Player, RoleKey
from backend.rules import assign_players, choose_false_lead, first_night_info, set_link
from backend.rules.powers import FALSE_LEAD_KEY


def _info_text(state: GameState, info) -> str:
    subjects = ", ".join(state.player(pid).name for pid in info.subject_ids)
    if info.kind == "demon":
        # Le complice voit le démon
        return f"Première nuit : tu es l'Apothicaire. Le Faucheur est : {subjects}."
    if info.kind == "accomplice":
        # Le démon voit le complice
        return f"Première nuit : tu es le Faucheur. Tes alliés sont : {subjects}."
    # L'Inquisiteur voit un complice parmi deux joueurs
    return f"Première nuit : parmi {subjects}, l'un d'eux est l'Apothicaire."


def check_unique_names(names: dict[str, str]) -> None:
    """Les noms servent à traduire les réponses des IA : ils doivent être uniques (sans tenir compte de la casse)."""
    if len({name.casefold() for name in names.values()}) != len(names):
        raise ValueError("noms de joueurs en double")


def setup_game(
    names: dict[str, str],
    human_id: str,
    personality_names: list[str],
    rng: random.Random,
    prompt_loader: Optional[PromptLoader] = None,
):
    """Met en place une partie : rôles, personnalités, fausse piste du Médium,
    agents IA et infos de première nuit. Renvoie (état, agents, mémoire)."""
    check_unique_names(names)
    assignments = assign_players(names, human_id, personality_names, rng)

    players = tuple(
        Player(id=player_id, name=assignment.name, role=assignment.role)
        for player_id, assignment in assignments.items()
    )
    state = GameState(turn=1, phase=Phase.NIGHT, players=players)

    roles = {player.id: player.role for player in players}
    false_lead = choose_false_lead(roles, rng)
    medium = next(player for player in players if player.role.name_EN == RoleKey.MEDIUM)
    state = state.replace_player(set_link(medium, FALSE_LEAD_KEY, false_lead))

    memory = MemoryManager(list(names), names=names)
    agents = create_all_agents(assignments, memory, human_id, prompt_loader)

    memory.set_moment(state.turn, state.phase)
    for info in first_night_info(state, rng):
        memory.add_event(
            EventType.ROLE_INFO,
            game_master,
            _info_text(state, info),
            frozenset({info.viewer_id}),
        )

    return state, agents, memory
