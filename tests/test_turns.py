import asyncio
import random

import pytest

import backend.agent_whispers as agent_whispers

from backend.game_engine import setup_game
from backend.turns import play_turn
from backend.models import Equipe, EventType, Phase

NAMES = {"h": "Alex", "p1": "Ada", "p2": "Bob", "p3": "Cléo", "p4": "Dan", "p5": "Eva"}
HUMAN_ID = "h"
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


@pytest.fixture(autouse=True)
def fake_whisper_llm(monkeypatch):
    """Résumés de la conversation simulée entre deux agents : aucun appel réseau."""
    async def fake(profile, messages, schema, context=None):
        return schema(resume_1="résumé du premier", resume_2="résumé du second")

    monkeypatch.setattr(agent_whispers, "ask_llm_json", fake)


class FakeAgent:
    """Agent IA factice : ne choisit rien, ne parle pas en public, répond en privé."""

    def __init__(self, player_id, personality_key="observer"):
        self.player_id = player_id
        self.personality_key = personality_key

    async def night_action(self, options, number_of_targets=1, situation=""):
        return []

    async def vote(self, options):
        return None

    async def speak_public(self, optional=False):
        return None

    async def speak_private(self, partners, opening=False):
        return f"{'ouverture' if opening else 'réponse'} de {self.player_id}"


class FakeHuman:
    """Humain factice : suit une liste de messages privés, puis se tait.
    partners=None : ne décide rien à temps ; accept_invitation : sa réponse à l'agent qui vient le voir."""

    def __init__(self, partners=(), messages=(), accept_invitation=False):
        self.partners = None if partners is None else list(partners)
        self.messages = list(messages)
        self.accept_invitation = accept_invitation
        self.invited_by = None
        self.meetings_seen = []
        self.deaths_seen = None
        self.replies_seen = []
        self.night_infos = []
        self.public_seen = []

    async def night_choice(self, state, player_id):
        return ()

    async def show_night_info(self, state, turn, info, allies):
        self.night_infos.append((turn, info, allies))

    async def show_night_deaths(self, state, deaths):
        self.deaths_seen = deaths

    async def show_public_message(self, state, author, text):
        self.public_seen.append((author, text))

    async def public_message(self, state, player_id):
        return None

    async def private_partners(self, state, player_id):
        return self.partners

    async def agent_invitation(self, state, player_id, agent_id):
        self.invited_by = agent_id
        return self.accept_invitation

    async def private_message(self, state, player_id):
        return self.messages.pop(0) if self.messages else None

    async def show_private_replies(self, state, replies):
        self.replies_seen.append(replies)

    async def show_agent_meeting(self, state, agent_ids):
        self.meetings_seen.append(agent_ids)

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

    result = asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.deaths_seen is not None
    assert result.game_winner is not None or result.state.phase == Phase.NUIT


def test_private_channel_message_reaches_only_its_partners():
    state, agents, memory, rng = _setup()
    partner_ids = list(agents)[:2]
    human = FakeHuman(partners=partner_ids, messages=["bonjour"])

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

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

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    stored = [e for e in memory.events_for(HUMAN_ID) if e.type == EventType.private_summary]
    contents = [e.content for e in stored]
    for batch in human.replies_seen:
        for _, text in batch:
            assert text in contents

# --- Sans décision du joueur, un agent vient lui proposer un entretien -----------

def _setup_with_personalities():
    """Agents aux personnalités distinctes : p3 est l'agitateur, le plus bavard."""
    state, _, memory, rng = _setup()
    keys = {"p1": "observer", "p2": "strategist", "p3": "agitator", "p4": "clown", "p5": "paranoid"}
    agents = {pid: FakeAgent(pid, key) for pid, key in keys.items()}
    return state, agents, memory, rng


def test_no_decision_brings_an_agent_who_speaks_first():
    state, agents, memory, rng = _setup_with_personalities()
    human = FakeHuman(partners=None, messages=["bonjour"], accept_invitation=True)

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.invited_by == "p3"  # agitateur, jamais rencontré en privé
    assert human.replies_seen[0] == [("p3", "ouverture de p3")]  # l'agent ouvre la conversation
    assert human.replies_seen[1] == [("p3", "réponse de p3")]    # puis répond au joueur
    assert memory.private_partners(HUMAN_ID) == {"p3"}


def test_refused_invitation_opens_no_channel():
    state, agents, memory, rng = _setup_with_personalities()
    human = FakeHuman(partners=None, messages=["bonjour"], accept_invitation=False)

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.invited_by == "p3"
    assert human.replies_seen == []
    assert memory.private_partners(HUMAN_ID) == set()
    assert all(e.type != EventType.private_meeting for e in memory.events_for(HUMAN_ID))


def test_invitation_comes_from_an_agent_never_met_in_private():
    state, agents, memory, rng = _setup_with_personalities()
    memory.add_private(EventType.private_summary, HUMAN_ID, "salut", {"p3"})
    human = FakeHuman(partners=None)

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.invited_by == "p5"  # paranoïaque : le suivant, l'agitateur a déjà parlé avec lui


def test_a_dead_agent_can_come_to_talk():
    state, _, memory, rng = _setup()
    # L'agitateur (le plus bavard) est un agent mort, qui n'est pas le Démon (sinon la partie s'arrête)
    dead = next(p.id for p in state.players if p.id != HUMAN_ID and p.role.team != Equipe.DEMON)
    agents = {p.id: FakeAgent(p.id, "agitator" if p.id == dead else "observer")
              for p in state.players if p.id != HUMAN_ID}
    state = state.replace_player(state.player(dead).die())
    human = FakeHuman(partners=None, accept_invitation=True)

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.invited_by == dead
    assert human.replies_seen[0] == [(dead, f"ouverture de {dead}")]


def test_human_can_open_a_channel_with_a_dead_agent():
    state, agents, memory, rng = _setup()
    dead = next(p.id for p in state.players if p.id != HUMAN_ID and p.role.team != Equipe.DEMON)
    state = state.replace_player(state.player(dead).die())
    human = FakeHuman(partners=[dead], messages=["bonjour"])

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.replies_seen[0] == [(dead, f"réponse de {dead}")]


def test_explicit_skip_brings_no_agent():
    state, agents, memory, rng = _setup_with_personalities()
    human = FakeHuman(partners=[])

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.invited_by is None


# --- Conversation simulée entre deux agents, pendant le salon du joueur -------------

def test_two_other_agents_meet_while_the_human_talks_in_private():
    state, agents, memory, rng = _setup()
    partner = list(agents)[0]
    human = FakeHuman(partners=[partner], messages=["bonjour"])

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert len(human.meetings_seen) == 1
    first, second = human.meetings_seen[0]
    assert {first, second}.isdisjoint({HUMAN_ID, partner})
    # Un résumé par agent, dans sa seule mémoire personnelle
    summaries = [e for e in memory.events_for(first) if e.type == EventType.private_summary]
    assert [e.visible_to for e in summaries] == [frozenset({first})]
    assert "résumé du premier" in summaries[0].content
    assert all("résumé" not in e.content for e in memory.events_for(HUMAN_ID))
    # Annonce publique, connue de tous les agents
    assert any(e.type == EventType.private_meeting and memory.name_of(second) in e.content
               for e in memory.events_for(partner))


def test_no_agent_meeting_when_the_human_skips_the_private_channel():
    state, agents, memory, rng = _setup()
    human = FakeHuman(partners=[])

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.meetings_seen == []
    assert memory.meetings() == []


def test_no_agent_meeting_when_the_invitation_is_refused():
    state, agents, memory, rng = _setup_with_personalities()
    human = FakeHuman(partners=None, accept_invitation=False)

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    assert human.meetings_seen == []


# --- Morts, votes et exécution dans la mémoire des agents ---------------------------

def test_agents_learn_deaths_votes_and_execution():
    state, agents, memory, rng = _setup()
    human = FakeHuman()

    asyncio.run(play_turn(state, rng, agents, memory, HUMAN_ID, human))

    public = [e.content for e in memory.events_for("p1") if e.visible_to is None]
    assert public == [
        "Personne n'est mort cette nuit.",
        "Votes : Alex → personne, Ada → personne, Bob → personne, Cléo → personne, Dan → personne, Eva → personne.",
        "Personne n'est exécuté aujourd'hui.",
    ]
