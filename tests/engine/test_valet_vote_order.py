"""Le Valet vote après son maître, et seulement si celui-ci a voté : aucun vote à annuler,
donc aucune mention qui révélerait son rôle, et pas d'appel LLM inutile."""
import asyncio

from backend.engine.turn import _collect_votes
from backend.models import GameState, Phase, Player
from backend.rules import get_role

NAMES = {"h": "Alex", "a": "Ada", "b": "Bob", "c": "Cléo", "v": "Val"}
ROLES = {"h": "medium", "a": "reaper", "b": "apothecary", "c": "watchman", "v": "valet"}


def game(master="a", human_role="medium"):
    roles = dict(ROLES, h=human_role)
    if human_role == "valet":
        roles["v"] = "inquisitor"
    players = []
    for pid in NAMES:
        links = {"master": master} if roles[pid] == "valet" else {}
        players.append(Player(id=pid, name=NAMES[pid], role=get_role(roles[pid]), links=links))
    return GameState(turn=2, phase=Phase.VOTE, players=tuple(players))


class Agent:
    def __init__(self, pid, choice, calls):
        self.player_id, self.choice, self.calls = pid, choice, calls

    async def vote(self, options):
        self.calls.append(self.player_id)
        return self.choice


class Human:
    def __init__(self, choice=None):
        self.choice, self.asked, self.blocked_by = choice, False, None

    async def vote(self, state, player_id):
        self.asked = True
        return self.choice

    async def show_valet_blocked(self, state, master_id):
        self.blocked_by = master_id

    async def show_agent_unavailable(self, state, agent_id, step):
        pass


def agents(choices, calls):
    return {pid: Agent(pid, choice, calls) for pid, choice in choices.items()}


def test_ai_valet_not_asked_when_his_master_abstains():
    calls = []
    votes, _ = asyncio.run(_collect_votes(game(), agents({"a": None, "b": "Cléo", "c": "Bob", "v": "Cléo"}, calls),
                                          "h", Human()))
    assert votes["v"] is None
    assert "v" not in calls  # pas d'appel LLM inutile


def test_ai_valet_votes_after_his_master():
    calls = []
    votes, _ = asyncio.run(_collect_votes(game(), agents({"a": "Cléo", "b": "Cléo", "c": "Bob", "v": "Cléo"}, calls),
                                          "h", Human()))
    assert votes["v"] == "c"
    assert calls[-1] == "v" and calls.index("a") < calls.index("v")


def test_ai_valet_whose_master_is_the_human_waits_for_the_human_vote():
    calls = []
    human = Human(choice="b")
    votes, _ = asyncio.run(_collect_votes(game(master="h"), agents({"a": None, "b": None, "c": None, "v": "Bob"}, calls),
                                          "h", human))
    assert human.asked and votes["h"] == "b"
    assert votes["v"] == "b"


def test_human_valet_is_told_privately_and_not_asked_when_his_master_abstains():
    human = Human(choice="a")
    votes, _ = asyncio.run(_collect_votes(game(human_role="valet"), agents({"a": None, "b": None, "c": None, "v": None}, []),
                                          "h", human))
    assert not human.asked
    assert human.blocked_by == "a"
    assert votes["h"] is None


def test_human_valet_votes_when_his_master_voted():
    human = Human(choice="a")
    votes, _ = asyncio.run(_collect_votes(game(human_role="valet", master="b"),
                                          agents({"a": None, "b": "Ada", "c": None, "v": None}, []), "h", human))
    assert human.asked and votes["h"] == "a"
