import asyncio
import random

import pytest

from backend.ai_turns import (
    check_unique_names,
    collect_ai_night_choices,
    collect_ai_votes,
    play_turn_with_ai,
)
from backend.memory_manager import MemoryManager
from backend.models import EventType, GameState, Phase, Player
from backend.rules import get_role

NAMES = {"a": "Ada", "b": "Bob", "c": "Cléo", "d": "Dan", "e": "Eva", "f": "Fay"}
ROLES = {"a": "imp", "b": "poisoner", "c": "monk", "d": "psychic", "e": "detective", "f": "butler"}


def night_game() -> GameState:
    players = tuple(Player(id=pid, name=NAMES[pid], role=get_role(ROLES[pid])) for pid in NAMES)
    return GameState(turn=2, phase=Phase.NUIT, players=players, channels=())


class FakeAgent:
    def __init__(self, pid, night=None, vote=None, speak=None):
        self.player_id = pid
        self.personality_key = "observer"
        self.night_reply = night
        self.vote_reply = vote
        self.speak_reply = speak
        self.seen_options = None

    async def night_action(self, options, number_of_targets=1):
        self.seen_options = options
        if self.night_reply is None:
            raise RuntimeError("panne")
        return self.night_reply(options, number_of_targets)

    async def vote(self, options):
        if self.vote_reply is None:
            raise RuntimeError("panne")
        return self.vote_reply(options)

    async def speak_public(self, optional=False):
        if self.speak_reply is None:
            return None
        return self.speak_reply()


def first_options(options, count):
    return list(options[:count])


def everyone(**kwargs):
    return {pid: FakeAgent(pid, **kwargs) for pid in NAMES}


def test_options_are_names_and_choice_is_an_id():
    agent = FakeAgent("a", night=first_options)
    choices = asyncio.run(collect_ai_night_choices(night_game(), {"a": agent}))
    assert "Ada" not in agent.seen_options
    assert "Bob" in agent.seen_options
    assert choices["a"] == ("b",)


def test_failing_night_agent_gives_empty_choice():
    choices = asyncio.run(collect_ai_night_choices(night_game(), {"a": FakeAgent("a")}))
    assert choices["a"] == ()


def test_vote_names_become_ids():
    votes = asyncio.run(collect_ai_votes(night_game(), everyone(vote=lambda options: "Cléo")))
    assert set(votes.values()) == {"c"}


def test_abstention_is_none():
    votes = asyncio.run(collect_ai_votes(night_game(), everyone(vote=lambda options: None)))
    assert all(target is None for target in votes.values())


def test_failing_voter_abstains():
    votes = asyncio.run(collect_ai_votes(night_game(), {"a": FakeAgent("a")}))
    assert votes == {"a": None}


def test_turn_with_ai_executes_the_chosen_player():
    memory = MemoryManager(list(NAMES))
    agents = everyone(night=first_options, vote=lambda options: "Cléo")
    result = asyncio.run(play_turn_with_ai(night_game(), random.Random(1), agents, memory))
    assert result.executed == "c"
    assert not result.state.player("c").alive
    assert result.game_winner is None


def test_public_messages_are_recorded_during_discussion():
    memory = MemoryManager(list(NAMES))
    agents = everyone(night=first_options, vote=lambda options: None, speak=lambda: "Bonjour")
    asyncio.run(play_turn_with_ai(night_game(), random.Random(1), agents, memory))
    messages = [e for e in memory.events_for("a") if e.type == EventType.public_message]
    assert messages
    assert all(e.phase == Phase.DISCUSSION and e.turn == 2 for e in messages)


def test_duplicate_names_are_refused():
    with pytest.raises(ValueError):
        check_unique_names({"a": "Ada", "b": "Ada"})