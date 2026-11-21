"""Boucle de tour (backend/engine/turn.py), jouée par de faux agents (aucun appel LLM) et un joueur automatique
à la place de l'humain : c'est la même boucle que celle du serveur."""
import asyncio
import random

import pytest

from backend.engine.human_port import AutoHumanPort
from backend.ai.memory_manager import MemoryManager
from backend.models import Alignment, EventType, GameState, Phase, Player
from backend.rules import get_role
from backend.engine.turn import play_turn

NAMES = {"a": "Ada", "b": "Bob", "c": "Cléo", "d": "Dan", "e": "Eva", "f": "Fay"}
ROLES = {"a": "imp", "b": "poisoner", "c": "monk", "d": "psychic", "e": "detective", "f": "butler"}
HUMAN = "f"  # le Majordome n'a pas d'agent : joueur automatique


class FakeAgent:
    """Agent sans LLM : premier choix légal la nuit, vote fixé, ne parle pas (sauf `speak`)."""

    def __init__(self, pid, vote=None, speak=None):
        self.player_id = pid
        self.personality_key = "observer"
        self.vote_for = vote
        self.speak = speak

    async def night_action(self, options, count=1, situation=""):
        return list(options[:count])

    async def vote(self, options):
        return self.vote_for if self.vote_for in options else None

    async def speak_public(self, optional=False):
        return self.speak


def game(turn=2) -> GameState:
    players = tuple(Player(id=pid, name=NAMES[pid], role=get_role(ROLES[pid])) for pid in NAMES)
    return GameState(turn=turn, phase=Phase.NIGHT, players=players)


def agents(**kwargs):
    return {pid: FakeAgent(pid, **kwargs) for pid in NAMES if pid != HUMAN}


def turn(state, agents, memory=None, seed=1):
    memory = memory or MemoryManager(list(NAMES), names=NAMES)
    return asyncio.run(play_turn(state, random.Random(seed), agents, memory, HUMAN, AutoHumanPort()))


def test_turn_without_execution_moves_to_next_night():
    result = turn(game(), agents())
    assert result.game_winner is None
    assert result.executed is None
    assert result.state.phase == Phase.NIGHT and result.state.turn == 3


def test_turn_requires_night_phase():
    with pytest.raises(ValueError):
        turn(game().next_phase(), agents())


def test_the_chosen_player_is_executed():
    result = turn(game(), agents(vote="Cléo"))
    assert result.executed == "c"
    assert not result.state.player("c").alive


def test_executing_the_demon_gives_good_the_win():
    result = turn(game(), agents(vote="Ada"))
    assert result.executed == "a"
    assert result.game_winner == Alignment.GOOD


def test_public_messages_are_recorded_during_discussion():
    memory = MemoryManager(list(NAMES), names=NAMES)
    turn(game(), agents(speak="Bonjour"), memory)
    messages = [e for e in memory.events_for("a") if e.type == EventType.PUBLIC_MESSAGE]
    assert messages
    assert all(e.phase == Phase.DISCUSSION and e.turn == 2 for e in messages)


def test_everyone_learns_deaths_votes_and_execution():
    memory = MemoryManager(list(NAMES), names=NAMES)
    turn(game(), agents(vote="Cléo"), memory)
    seen = [(e.type, e.phase, e.content) for e in memory.events_for("e") if e.visible_to is None]
    deaths = [s for s in seen if s[0] == EventType.DEATH]
    assert deaths[0][1] == Phase.NIGHT  # au réveil : morts de la nuit (ou personne)
    assert deaths[-1] == (EventType.DEATH, Phase.VOTE, "Cléo est exécuté·e par le village.")
    [vote] = [s for s in seen if s[0] == EventType.VOTE]
    assert "Cléo → personne" in vote[2]  # Cléo ne peut pas voter contre elle-même
    assert "Fay → personne" in vote[2]   # le joueur automatique s'abstient


def test_a_game_can_be_played_to_the_end():
    """Des tours successifs, comme les scripts « IA seules » : la partie finit par un vainqueur."""
    state, memory = game(turn=1), MemoryManager(list(NAMES), names=NAMES)
    for _ in range(10):
        result = turn(state, agents(vote="Ada"), memory)
        state = result.state
        if result.game_winner is not None:
            break
    assert result.game_winner is not None
