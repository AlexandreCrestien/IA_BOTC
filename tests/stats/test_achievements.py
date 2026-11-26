"""Succès : faits relevés tour par tour, et conditions de chaque succès."""
from types import SimpleNamespace

import pytest

from backend.engine.steps import Ballot
from backend.models import RoleKey
from backend.stats.achievements import ACHIEVEMENTS, BY_CODE, GameFacts, GameSummary, earned_achievements


def turn_result(executed=None, night_deaths=(), ballots=()):
    return SimpleNamespace(executed=executed, night_deaths=night_deaths, ballots=ballots)


def codes(**summary) -> set[str]:
    summary.setdefault("role", RoleKey.MEDIUM)
    summary.setdefault("won", False)
    summary.setdefault("turns", 5)
    return {a.code for a in earned_achievements(GameSummary(**summary))}


# --- Faits relevés pendant la partie ---------------------------------------------------

def test_facts_from_votes():
    facts = GameFacts()
    facts.record_turn("h", 1, turn_result(executed="p1", ballots=(Ballot("h", "p1", ghost=False),)))
    assert facts.voted_for_executed and not facts.ghost_vote_used


def test_vote_for_someone_not_executed_does_not_count():
    facts = GameFacts()
    facts.record_turn("h", 1, turn_result(executed="p2", ballots=(Ballot("h", "p1", ghost=False),)))
    facts.record_turn("h", 2, turn_result(executed=None, ballots=(Ballot("h", None, ghost=False),)))
    assert not facts.voted_for_executed


def test_other_players_ballots_are_ignored():
    facts = GameFacts()
    facts.record_turn("h", 1, turn_result(executed="p2", ballots=(Ballot("p1", "p2", ghost=True),)))
    assert facts == GameFacts()


def test_ghost_vote():
    facts = GameFacts()
    facts.record_turn("h", 3, turn_result(ballots=(Ballot("h", "p1", ghost=True),)))
    assert facts.ghost_vote_used


def test_executed_and_killed_at_night():
    facts = GameFacts()
    facts.record_turn("h", 2, turn_result(executed="h"))
    assert facts.executed_turn == 2 and not facts.killed_at_night
    other = GameFacts()
    other.record_turn("h", 2, turn_result(night_deaths=("h",)))
    assert other.killed_at_night and other.executed_turn is None


# --- Conditions des succès ---------------------------------------------------------------

@pytest.mark.parametrize("role", list(RoleKey))
def test_win_as_each_role(role):
    assert f"win_{role.value}" in codes(role=role, won=True)
    assert f"win_{role.value}" not in codes(role=role, won=False)


def test_a_defeat_still_gives_the_action_achievements():
    facts = GameFacts(ghost_vote_used=True, voted_for_executed=True, executed_turn=3)
    assert codes(facts=facts) == {"ghost_vote", "executioner", "executed"}


def test_quick_wins():
    assert {"quick_win", "one_turn_win"} <= codes(won=True, turns=1)
    assert "quick_win" in codes(won=True, turns=3)
    assert "one_turn_win" not in codes(won=True, turns=3)
    assert codes(won=True, turns=4) == {"win_medium"}
    assert "quick_win" not in codes(won=False, turns=1)


def test_executed_on_first_turn():
    assert {"executed", "executed_first_turn"} <= codes(facts=GameFacts(executed_turn=1))
    assert "executed_first_turn" not in codes(facts=GameFacts(executed_turn=2))


def test_win_after_execution_or_night_kill():
    assert "win_after_execution" in codes(won=True, facts=GameFacts(executed_turn=2))
    assert "win_after_execution" not in codes(won=False, facts=GameFacts(executed_turn=2))
    assert "win_after_reaper" in codes(won=True, facts=GameFacts(killed_at_night=True))
    assert "win_after_reaper" not in codes(won=False, facts=GameFacts(killed_at_night=True))


def test_definitions():
    assert len(ACHIEVEMENTS) == 14 and len(BY_CODE) == 14  # codes uniques
    hidden = {a.code for a in ACHIEVEMENTS if a.hidden}
    assert hidden == {"one_turn_win", "executed_first_turn", "win_after_execution", "win_after_reaper"}
    assert BY_CODE["one_turn_win"].message == "Talents de détective surnaturels ou chance inouïe ?"
