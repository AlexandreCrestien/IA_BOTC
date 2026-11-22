import random

from backend.models import Role
from backend.rules import assign_players

NAMES = {"h": "Alex", "p1": "Ada", "p2": "Bob", "p3": "Cléo", "p4": "Dan", "p5": "Eva"}
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


def test_each_player_gets_a_role_and_human_has_no_personality():
    assignments = assign_players(NAMES, "h", PERSONALITIES, random.Random(1))
    assert set(assignments) == set(NAMES)
    assert assignments["h"].personality is None
    assert assignments["h"].name == "Alex"
    assert len({assignments[p].role.name_EN for p in NAMES}) == 6
    assert all(isinstance(assignments[p].role, Role) for p in NAMES)


def test_ai_personalities_are_unique():
    assignments = assign_players(NAMES, "h", PERSONALITIES, random.Random(1))
    keys = [assignments[p].personality for p in NAMES if p != "h"]
    assert sorted(keys) == sorted(PERSONALITIES)


def test_same_seed_same_assignment():
    first = assign_players(NAMES, "h", PERSONALITIES, random.Random(42))
    second = assign_players(NAMES, "h", PERSONALITIES, random.Random(42))
    assert first == second


def test_unknown_human_raises():
    import pytest

    with pytest.raises(ValueError):
        assign_players(NAMES, "zz", PERSONALITIES, random.Random(1))

def test_duplicate_names_are_refused():
    import pytest

    with pytest.raises(ValueError):
        assign_players({"h": "Ada", "p1": "Ada", "p2": "Bob", "p3": "Cléo", "p4": "Dan", "p5": "Eva"},
                       "h", PERSONALITIES, random.Random(1))