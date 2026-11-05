import asyncio

import pytest

import backend.agent_factory as agent_factory
from backend.agent_factory import PASS, Agent
from backend.conversations import public_conversation
from backend.memory_manager import MemoryManager
from backend.models import Player
from backend.rules.catalogue import ROLES

IDS = ["ana", "bruno", "carla", "dan", "eva"]


@pytest.fixture
def memory():
    return MemoryManager(IDS)


def make_agents(memory, personalities):
    """Un agent par personnalité, dans l'ordre de IDS.
    Le prompt système est l'id du joueur : le faux LLM sait ainsi qui parle."""
    return [
        Agent(Player(id=i, name=i, role=ROLES["monk"]), p, memory, system_prompt=i, personality_key=p)
        for i, p in zip(IDS, personalities)
    ]


@pytest.fixture
def fake_llm(monkeypatch):
    """Remplace le LLM. Aucun appel réseau.

    fake_llm.reply(player_id, optional) : la réponse à renvoyer.
    fake_llm.calls : (player_id, optional) pour chaque appel.
    """
    class FakeLLM:
        def __init__(self):
            self.calls: list[tuple[str, bool]] = []
            self.reply = lambda player_id, optional: f"message de {player_id}"

        async def __call__(self, profile, messages, **kwargs):
            player_id = messages[0]["content"].split()[0]
            optional = PASS in messages[-1]["content"]
            self.calls.append((player_id, optional))
            return self.reply(player_id, optional)

    fake = FakeLLM()
    monkeypatch.setattr(agent_factory, "ask_llm", fake)
    return fake


def test_order_follows_personalities(memory, fake_llm):
    agents = make_agents(memory, ["observer", "strategist", "clown", "paranoid", "agitator"])
    said = asyncio.run(public_conversation(agents, memory, max_messages=5))
    # agitator (eva), paranoid (dan), clown (carla), strategist (bruno), observer (ana)
    assert [player for player, _ in said] == ["eva", "dan", "carla", "bruno", "ana"]


def test_stops_at_max_messages(memory, fake_llm):
    agents = make_agents(memory, ["agitator", "paranoid", "clown", "strategist", "observer"])
    said = asyncio.run(public_conversation(agents, memory))
    assert len(said) == 10
    assert len(fake_llm.calls) == 10  # pas d'appel inutile après la limite


def test_messages_are_saved_in_memory_for_everyone(memory, fake_llm):
    agents = make_agents(memory, ["agitator", "paranoid", "clown", "strategist", "observer"])
    asyncio.run(public_conversation(agents, memory, max_messages=2))
    for player in IDS:
        assert [e.content for e in memory.events_for(player)] == ["message de ana", "message de bruno"]


def test_only_optional_personalities_may_pass(memory, fake_llm):
    agents = make_agents(memory, ["agitator", "paranoid", "clown", "strategist", "observer"])
    asyncio.run(public_conversation(agents, memory, max_messages=5))
    assert fake_llm.calls == [("ana", False), ("bruno", False), ("carla", False), ("dan", True), ("eva", True)]


def test_optional_agent_can_pass(memory, fake_llm):
    fake_llm.reply = lambda player_id, optional: PASS if optional else f"message de {player_id}"
    agents = make_agents(memory, ["agitator", "strategist", "observer", "clown", "paranoid"])
    said = asyncio.run(public_conversation(agents, memory, max_messages=3))
    assert [player for player, _ in said] == ["ana", "eva", "dan"]


def test_stops_when_everybody_passes(memory, fake_llm):
    fake_llm.reply = lambda player_id, optional: PASS
    agents = make_agents(memory, ["strategist", "observer"])
    assert asyncio.run(public_conversation(agents, memory)) == []
    assert len(fake_llm.calls) == 2  # un seul tour, pas de boucle infinie


def test_failing_agent_is_skipped(memory, fake_llm):
    def reply(player_id, optional):
        if player_id == "ana":
            raise RuntimeError("tous les modèles ont échoué")
        return f"message de {player_id}"

    fake_llm.reply = reply
    agents = make_agents(memory, ["agitator", "paranoid"])
    said = asyncio.run(public_conversation(agents, memory, max_messages=2))
    assert said == [("bruno", "message de bruno"), ("bruno", "message de bruno")]


def test_personality_key_is_separate_from_display_name(memory):
    agent = Agent(Player(id="ana", name="ana", role=ROLES["monk"]), "Provocateur", memory, "prompt",
                  personality_key="agitator")
    assert agent.personality == "Provocateur"
    assert agent.personality_key == "agitator"
