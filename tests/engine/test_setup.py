import random

from backend.engine.setup import setup_game
from backend.models import Alignment, Phase

NAMES = {"h": "Alex", "p1": "Ada", "p2": "Bob", "p3": "Cléo", "p4": "Dan", "p5": "Eva"}
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


def test_setup_creates_six_players_and_five_agents():
    state, agents, _ = setup_game(NAMES, "h", PERSONALITIES, random.Random(1))
    assert len(state.players) == 6
    assert set(agents) == set(NAMES) - {"h"}
    assert state.turn == 1
    assert state.phase == Phase.NIGHT


def test_medium_gets_a_false_lead_among_good_players():
    state, _, _ = setup_game(NAMES, "h", PERSONALITIES, random.Random(1))
    medium = next(p for p in state.players if p.role.name_EN == "medium")
    false_lead = medium.links["false_lead"]
    assert false_lead != medium.id
    assert state.player(false_lead).role.alignment == Alignment.GOOD


def test_same_seed_same_game():
    first, _, _ = setup_game(NAMES, "h", PERSONALITIES, random.Random(42))
    second, _, _ = setup_game(NAMES, "h", PERSONALITIES, random.Random(42))
    assert first == second