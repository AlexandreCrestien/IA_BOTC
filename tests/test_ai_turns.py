import asyncio
import random

import pytest

from backend.ai_turns import (
    check_unique_names,
    collect_ai_ballots,
    collect_ai_night_choices,
    collect_ai_nomination,
    collect_ai_votes,
    play_turn_with_ai,
    final_vote,
    vote_on_nomination,
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
    def __init__(self, pid, night=None, vote=None, speak=None, nominate=None, ballot=None):
        self.player_id = pid
        self.name = NAMES[pid]
        self.nominate_reply = nominate
        self.ballot_reply = ballot
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

    async def nominate(self, options):
        if self.nominate_reply is None:
            return None
        return self.nominate_reply(options)

    async def vote_on(self, nominee):
        if self.ballot_reply is None:
            raise RuntimeError("panne")
        return self.ballot_reply(nominee)

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


def test_turn_with_ai_executes_the_nominated_player():
    memory = MemoryManager(list(NAMES))
    agents = everyone(night=first_options, nominate=lambda options: "Cléo", ballot=lambda nominee: True)
    result = asyncio.run(play_turn_with_ai(night_game(), random.Random(1), agents, memory))
    assert result.executed == "c"
    assert not result.state.player("c").alive
    assert result.game_winner is None


def test_without_nomination_everyone_votes_at_the_end_of_the_day():
    memory = MemoryManager(list(NAMES))
    agents = everyone(night=first_options, vote=lambda options: "Dan")
    result = asyncio.run(play_turn_with_ai(night_game(), random.Random(1), agents, memory))
    assert result.executed == "d"
    assert any(e.content.startswith("Fin du jour") for e in memory.events_for("a"))


def test_failed_nomination_is_followed_by_the_end_of_day_vote():
    memory = MemoryManager(list(NAMES))
    agents = everyone(night=first_options, nominate=lambda options: "Cléo", ballot=lambda nominee: False,
                      vote=lambda options: "Dan")
    result = asyncio.run(play_turn_with_ai(night_game(), random.Random(1), agents, memory))
    assert result.executed == "d"
    assert result.state.player("c").alive


def test_successful_nomination_skips_the_end_of_day_vote():
    memory = MemoryManager(list(NAMES))
    agents = everyone(night=first_options, nominate=lambda options: "Cléo", ballot=lambda nominee: True,
                      vote=lambda options: "Dan")
    result = asyncio.run(play_turn_with_ai(night_game(), random.Random(1), agents, memory))
    assert result.executed == "c" and result.state.player("d").alive
    assert not any(e.content.startswith("Fin du jour") for e in memory.events_for("a"))


def test_agents_do_not_nominate_twice_or_the_same_player():
    agents = everyone(nominate=lambda options: options[0])
    nomination = asyncio.run(collect_ai_nomination(day_game(), agents, frozenset({"a", "b", "c", "d", "e"}),
                                                   frozenset({"a"})))
    assert nomination is not None and nomination[0] == "f" and nomination[1] != "a"


def day_game() -> GameState:
    return night_game().next_phase()  # discussion


def test_first_agent_in_speaking_order_nominates():
    agents = everyone(nominate=lambda options: "Dan")
    agents["a"].personality_key = "agitator"  # parle en premier
    agents["a"].nominate_reply = lambda options: "Eva"
    assert asyncio.run(collect_ai_nomination(day_game(), agents)) == ("a", "e")


def test_agents_cannot_nominate_themselves_or_the_dead():
    state = day_game()
    state = state.replace_player(state.player("b").die())
    seen = {}
    agent = FakeAgent("a", nominate=lambda options: seen.setdefault("options", options) and None)
    asyncio.run(collect_ai_nomination(state, {"a": agent}))
    assert "Ada" not in seen["options"] and "Bob" not in seen["options"]


def test_dead_agent_does_not_nominate():
    state = day_game()
    state = state.replace_player(state.player("a").die())
    agent = FakeAgent("a", nominate=lambda options: "Bob")
    assert asyncio.run(collect_ai_nomination(state, {"a": agent})) is None


def test_failing_ballot_counts_as_against():
    ballots = asyncio.run(collect_ai_ballots(day_game(), {"a": FakeAgent("a")}, "c"))
    assert ballots == {"a": False}


def test_majority_of_voters_is_needed():
    """3 pour sur 6 votants : égalité, personne n'est exécuté."""
    memory = MemoryManager(list(NAMES))
    agents = everyone(ballot=lambda nominee: False)
    for pid in ("a", "b", "d"):
        agents[pid].ballot_reply = lambda nominee: True
    state = day_game().next_phase()
    after, votes, executed = asyncio.run(vote_on_nomination(state, agents, memory, ("a", "c")))
    assert executed is None and after.player("c").alive
    assert any(e.content.startswith("Vote sur Cléo : pour (3)") for e in memory.events_for("e"))


def test_nomination_is_announced_by_the_nominator():
    memory = MemoryManager(list(NAMES), names=NAMES)
    agents = everyone(ballot=lambda nominee: True)
    asyncio.run(vote_on_nomination(day_game().next_phase(), agents, memory, ("a", "c")))
    first = memory.events_for("b")[0]
    assert first.type == EventType.nomination and first.author_id == "a"
    assert "Cléo" in first.content


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

def test_dead_human_who_voted_for_is_not_asked_again():
    """Une morte vote « pour » sur une désignation : son vote fantôme est utilisé,
    elle n'est plus appelée au vote de fin de jour."""
    state = day_game()
    state = state.replace_player(state.player("f").die())
    agents = {pid: agent for pid, agent in everyone(ballot=lambda nominee: False,
                                                     vote=lambda options: None).items() if pid != "f"}
    memory = MemoryManager(list(NAMES))
    asked = []

    async def human_ballot(vote_state):
        asked.append("désignation")
        return {"f": True} if vote_state.player("f").can_vote else {}

    async def human_final(vote_state):
        if vote_state.player("f").can_vote:
            asked.append("fin de jour")
            return {"f": "c"}
        return {}

    async def play():
        after, _, _ = await vote_on_nomination(state, agents, memory, ("a", "c"), human_ballot)
        assert not after.player("f").can_vote
        await final_vote(after.next_phase(), agents, memory, human_final)

    asyncio.run(play())
    assert asked == ["désignation"]
