import asyncio

import pytest

import backend.agent_factory as agent_factory
from backend.agent_factory import PASS, Agent
from backend.conversations import (
    choose_agent_for_human,
    private_message,
    public_conversation,
    start_private_conversation,
)
from backend.memory_manager import MemoryManager
from backend.models import EventType, Player
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


# --- Conversation privée -----------------------------------------------------

HUMAN = "eva"


def test_choose_most_talkative_first(memory):
    agents = make_agents(memory, ["observer", "clown", "agitator", "strategist"])
    assert choose_agent_for_human(agents, HUMAN, memory).player_id == "carla"  # agitator


def test_choose_agent_who_never_talked_with_human(memory):
    agents = make_agents(memory, ["observer", "clown", "agitator", "strategist"])
    memory.add_private(EventType.private_summary, HUMAN, "salut", {"carla"})
    assert choose_agent_for_human(agents, HUMAN, memory).player_id == "bruno"  # clown, le suivant


def test_choose_anybody_when_everybody_already_talked(memory):
    agents = make_agents(memory, ["observer", "agitator"])
    memory.add_private(EventType.private_summary, HUMAN, "salut", {"ana", "bruno"})
    assert choose_agent_for_human(agents, HUMAN, memory).player_id == "bruno"


def test_start_announces_meeting_publicly_without_content(memory, fake_llm):
    agents = make_agents(memory, ["agitator", "clown"])
    said = asyncio.run(start_private_conversation(HUMAN, agents, memory))
    assert said == []
    assert [e.type for e in memory.events_for("dan")] == [EventType.private_meeting]
    assert fake_llm.calls == []  # l'humain parle en premier : pas d'appel au LLM


def test_agent_can_speak_first(memory, fake_llm):
    agent = make_agents(memory, ["agitator"])
    said = asyncio.run(start_private_conversation(HUMAN, agent, memory, agent_speaks_first=True))
    assert said == [("ana", "message de ana")]


def test_private_message_gets_replies_from_each_agent(memory, fake_llm):
    agents = make_agents(memory, ["agitator", "clown"])
    said = asyncio.run(private_message(HUMAN, "Qui suspectez-vous ?", agents, memory))
    assert said == [("ana", "message de ana"), ("bruno", "message de bruno")]
    assert [e.content for e in memory.events_for("bruno")] == [
        "Qui suspectez-vous ?", "message de ana", "message de bruno"]


def test_private_content_stays_secret(memory, fake_llm):
    agents = make_agents(memory, ["agitator"])
    asyncio.run(start_private_conversation(HUMAN, agents, memory))
    asyncio.run(private_message(HUMAN, "SECRET", agents, memory))
    for outsider in ["bruno", "carla", "dan"]:
        assert all("SECRET" not in e.content for e in memory.events_for(outsider))
        assert memory.private_partners(outsider) == set()
    assert memory.private_partners(HUMAN) == {"ana"}


def test_failing_agent_does_not_stop_private_conversation(memory, fake_llm):
    def reply(player_id, optional):
        if player_id == "ana":
            raise RuntimeError("tous les modèles ont échoué")
        return f"message de {player_id}"

    fake_llm.reply = reply
    agents = make_agents(memory, ["agitator", "clown"])
    assert asyncio.run(private_message(HUMAN, "Salut", agents, memory)) == [("bruno", "message de bruno")]


@pytest.mark.parametrize("count", [0, 3])
def test_private_conversation_needs_one_or_two_agents(memory, count):
    agents = make_agents(memory, ["agitator", "clown", "observer"])[:count]
    with pytest.raises(ValueError, match="1 ou 2"):
        asyncio.run(private_message(HUMAN, "Salut", agents, memory))


# --- Cas limites ---------------------------------------------------------------

def test_unknown_personality_speaks_last_and_may_pass(memory, fake_llm):
    agents = make_agents(memory, ["inconnue", "agitator"])
    asyncio.run(public_conversation(agents, memory, max_messages=2))
    assert fake_llm.calls == [("bruno", False), ("ana", True)]


def test_choose_agent_without_agents_raises(memory):
    with pytest.raises(ValueError, match="Aucun agent"):
        choose_agent_for_human([], HUMAN, memory)


def test_human_cannot_talk_privately_with_himself(memory):
    agents = make_agents(memory, ["agitator", "clown", "observer", "paranoid", "strategist"])
    with pytest.raises(ValueError, match="propre interlocuteur"):
        asyncio.run(start_private_conversation(HUMAN, [agents[4]], memory))  # agents[4] = eva = HUMAN


def test_meeting_announcement_uses_names(fake_llm):
    memory = MemoryManager(IDS, names={i: i.capitalize() for i in IDS})
    agents = make_agents(memory, ["clown"])
    asyncio.run(start_private_conversation("eva", agents, memory))
    assert memory.events_for("dan")[0].content == "Conversation privée entre Eva, Ana."
