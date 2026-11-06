import asyncio
import random

from backend.game_engine import setup_game
from backend.human_turns import play_turn_with_human
from backend.models import EventType, Phase

NAMES = {"h": "Alex", "p1": "Ada", "p2": "Bob", "p3": "Cléo", "p4": "Dan", "p5": "Eva"}
HUMAN_ID = "h"
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


class FakeAgent:
    """Agent IA factice : ne choisit rien, ne parle pas en public, répond en privé."""

    def __init__(self, player_id):
        self.player_id = player_id
        self.personality_key = "observer"

    async def night_action(self, options, number_of_targets=1):
        return []

    async def vote(self, options):
        return None

    async def speak_public(self, optional=False):
        return None

    async def speak_private(self, partners):
        return f"réponse de {self.player_id}"


class FakeHuman:
    """Humain factice : suit une liste de messages privés, puis se tait."""

    def __init__(self, partners=(), messages=()):
        self.partners = list(partners)
        self.messages = list(messages)
        self.deaths_seen = None
        self.replies_seen = []

    async def night_choice(self, state, player_id):
        return ()

    async def show_night_deaths(self, state, deaths):
        self.deaths_seen = deaths

    async def public_message(self, state, player_id):
        return None

    async def private_partners(self, state, player_id):
        return self.partners

    async def private_message(self, state, player_id):
        return self.messages.pop(0) if self.messages else None

    async def show_private_replies(self, replies):
        self.replies_seen.append(replies)

    async def vote(self, state, player_id):
        return None


def _setup():
    rng = random.Random(0)
    state, _, memory = setup_game(NAMES, HUMAN_ID, PERSONALITIES, rng)
    agents = {p.id: FakeAgent(p.id) for p in state.players if p.id != HUMAN_ID}
    return state, agents, memory, rng


def test_turn_with_human_completes_and_shows_deaths():
    state, agents, memory, rng = _setup()
    human = FakeHuman()

    result = asyncio.run(play_turn_with_human(state, rng, agents, memory, HUMAN_ID, human))

    assert human.deaths_seen is not None
    assert result.game_winner is not None or result.state.phase == Phase.NUIT


def test_private_channel_message_reaches_only_its_partners():
    state, agents, memory, rng = _setup()
    partner_ids = list(agents)[:2]
    human = FakeHuman(partners=partner_ids, messages=["bonjour"])

    asyncio.run(play_turn_with_human(state, rng, agents, memory, HUMAN_ID, human))

    # Au plus un partenaire peut mourir pendant la nuit 1 : il reste au moins une réponse.
    replies = [(pid, text) for batch in human.replies_seen for pid, text in batch]
    assert len(replies) >= 1
    for pid, text in replies:
        assert pid in partner_ids
        assert text == f"réponse de {pid}"
    assert any(e.content == "bonjour" for e in memory.events_for(HUMAN_ID))


def test_private_channel_replies_are_stored_for_the_human():
    state, agents, memory, rng = _setup()
    partner_ids = list(agents)[:2]
    human = FakeHuman(partners=partner_ids, messages=["bonjour"])

    asyncio.run(play_turn_with_human(state, rng, agents, memory, HUMAN_ID, human))

    stored = [e for e in memory.events_for(HUMAN_ID) if e.type == EventType.private_summary]
    contents = [e.content for e in stored]
    for batch in human.replies_seen:
        for _, text in batch:
            assert text in contents