import asyncio

import pytest

from backend.ai.choices import (
    collect_ai_night_choices,
    collect_ai_votes,
)
from backend.engine.setup import check_unique_names
from backend.models import GameState, Phase, Player
from backend.rules import get_role

NAMES = {"a": "Ada", "b": "Bob", "c": "Cléo", "d": "Dan", "e": "Eva", "f": "Fay"}
ROLES = {"a": "imp", "b": "poisoner", "c": "monk", "d": "psychic", "e": "detective", "f": "butler"}


def night_game() -> GameState:
    players = tuple(Player(id=pid, name=NAMES[pid], role=get_role(ROLES[pid])) for pid in NAMES)
    return GameState(turn=2, phase=Phase.NIGHT, players=players)


class FakeAgent:
    def __init__(self, pid, night=None, vote=None, speak=None):
        self.player_id = pid
        self.personality_key = "observer"
        self.night_reply = night
        self.vote_reply = vote
        self.speak_reply = speak
        self.seen_options = None

    async def night_action(self, options, count=1, situation=""):
        self.seen_options = options
        if self.night_reply is None:
            raise RuntimeError("panne")
        return self.night_reply(options, count)

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


def test_duplicate_names_are_refused():
    with pytest.raises(ValueError):
        check_unique_names({"a": "Ada", "b": "Ada"})

def test_ai_vote_options_exclude_the_voter():
    seen = {}

    def remember(pid):
        def vote(options):
            seen[pid] = options
            return None
        return vote

    agents = {pid: FakeAgent(pid, vote=remember(pid)) for pid in NAMES}
    asyncio.run(collect_ai_votes(night_game(), agents))
    for pid, options in seen.items():
        assert NAMES[pid] not in options
        assert len(options) == len(NAMES) - 1
