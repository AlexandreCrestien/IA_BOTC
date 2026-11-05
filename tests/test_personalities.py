import random

import pytest

from backend.rules.distribution import distribute_personalities

PERSONALITIES = [
    {"personality_name_EN": n, "personality_name_FR": n}
    for n in ["paranoid", "clown", "agitator", "observer", "strategist"]
]


def test_each_ai_gets_a_different_personality():
    result = distribute_personalities(["p1", "p2", "p3", "p4", "p5"], PERSONALITIES, random.Random(1))
    names = [data["personality_name_EN"] for data in result.values()]
    assert sorted(names) == sorted(p["personality_name_EN"] for p in PERSONALITIES)


def test_not_enough_personalities_raises():
    with pytest.raises(ValueError):
        distribute_personalities(["p1", "p2", "p3", "p4", "p5", "p6"], PERSONALITIES, random.Random(1))


def test_same_seed_same_result():
    first = distribute_personalities(["p1", "p2"], PERSONALITIES, random.Random(7))
    second = distribute_personalities(["p1", "p2"], PERSONALITIES, random.Random(7))
    assert first == second


def test_input_order_does_not_change_result():
    reversed_list = list(reversed(PERSONALITIES))
    first = distribute_personalities(["p1", "p2"], PERSONALITIES, random.Random(7))
    second = distribute_personalities(["p1", "p2"], reversed_list, random.Random(7))
    assert first == second


def test_no_ai_players_gives_empty_dict():
    assert distribute_personalities([], PERSONALITIES, random.Random(1)) == {}