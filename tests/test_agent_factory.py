import asyncio

import pytest
from pydantic import ValidationError

import backend.agent_factory as agent_factory
import backend.llm_client as llm_client
from backend.agent_factory import AGENT_RULES, Agent, NightAction, Nomination, create_agents
from backend.memory_manager import EventType, MemoryManager, game_master

ROLES = ["imp", "poisoner", "monk", "psychic", "detective", "butler"]
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


@pytest.fixture
def memory():
    return MemoryManager(["ana", "bruno", "carla"])


@pytest.fixture
def fake_llm(monkeypatch):
    """Remplace le LLM par des réponses préparées. Aucun appel réseau.

    fake_llm.replies : réponses renvoyées dans l'ordre.
    fake_llm.calls : messages reçus à chaque appel.
    """
    class FakeLLM:
        def __init__(self):
            self.replies: list[str] = []
            self.calls: list[list[dict]] = []

        async def __call__(self, profile, messages, **kwargs):
            self.calls.append(messages)
            return self.replies.pop(0)

    fake = FakeLLM()
    monkeypatch.setattr(llm_client, "ask_llm", fake)     # utilisé par ask_llm_json
    monkeypatch.setattr(agent_factory, "ask_llm", fake)  # utilisé par speak_public / speak_private
    return fake


# --- Prompt système ---------------------------------------------------------

def test_system_prompt_contains_all_parts(memory):
    prompt = Agent("ana", "imp", "clown", memory).system_prompt
    assert "Ton nom dans cette partie est ana" in prompt
    assert "Diablotin" in prompt                      # skill de rôle
    assert "Bouffon" in prompt                        # skill de personnalité
    assert "# RÈGLES ET CONTRAINTES STRICTES" in prompt  # general_rules.md
    assert AGENT_RULES in prompt
    assert "Joueurs présents dans la partie : ana, bruno, carla." in prompt


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("personality", PERSONALITIES)
def test_every_role_and_personality_loads(memory, role, personality):
    Agent("ana", role, personality, memory)


def test_unknown_role_raises(memory):
    with pytest.raises(FileNotFoundError):
        Agent("ana", "scarlet_woman", "clown", memory)


# --- Isolement --------------------------------------------------------------

def test_agent_never_sends_other_players_secrets(memory, fake_llm):
    memory.add_private(EventType.private_summary, "bruno", "SECRET", {"carla"})
    memory.add_personal(EventType.role_info, game_master, "Tu es le Moine.", "ana")
    fake_llm.replies = ["Bonjour !"]

    asyncio.run(Agent("ana", "monk", "observer", memory).speak_public())

    sent = " ".join(m["content"] for m in fake_llm.calls[0])
    assert "Tu es le Moine." in sent
    assert "SECRET" not in sent


# --- Validation des choix (sans LLM) ---------------------------------------

def test_night_action_accepts_legal_target():
    action = NightAction.model_validate_json(
        '{"cibles": ["bruno"], "raison": "x"}', context={"options": ["bruno", "carla"], "number_of_targets": 1}
    )
    assert action.cibles == ["bruno"]


def test_night_action_rejects_illegal_target():
    with pytest.raises(ValidationError, match="n'est pas un choix possible"):
        NightAction.model_validate_json(
            '{"cibles": ["ana"], "raison": "x"}', context={"options": ["bruno", "carla"], "number_of_targets": 1}
        )


def test_night_action_rejects_wrong_number_of_targets():
    with pytest.raises(ValidationError, match="exactement 2"):
        NightAction.model_validate_json(
            '{"cibles": ["bruno"], "raison": "x"}', context={"options": ["bruno", "carla"], "number_of_targets": 2}
        )


def test_nomination_rejects_illegal_target():
    with pytest.raises(ValidationError):
        Nomination.model_validate_json('{"cible": "zoe", "raison": "x"}', context={"options": ["bruno", "personne"]})


# --- Méthodes de l'agent avec un faux LLM -----------------------------------

def test_night_action_strips_code_fences(memory, fake_llm):
    fake_llm.replies = ['```json\n{"cibles": ["carla"], "raison": "x"}\n```']
    agent = Agent("ana", "imp", "strategist", memory)
    assert asyncio.run(agent.night_action(["bruno", "carla"])) == ["carla"]


def test_night_action_retries_after_illegal_target(memory, fake_llm):
    fake_llm.replies = ['{"cibles": ["ana"], "raison": "x"}', '{"cibles": ["bruno"], "raison": "x"}']
    agent = Agent("ana", "imp", "strategist", memory)
    assert asyncio.run(agent.night_action(["bruno", "carla"])) == ["bruno"]
    # Le second appel explique l'erreur au modèle
    assert "n'est pas un choix possible" in fake_llm.calls[1][-1]["content"]


def test_night_action_retries_after_refusal(memory, fake_llm):
    fake_llm.replies = ["I'm sorry, I can't help with that.", '{"cibles": ["carla"], "raison": "x"}']
    agent = Agent("ana", "imp", "strategist", memory)
    assert asyncio.run(agent.night_action(["bruno", "carla"])) == ["carla"]


def test_night_action_gives_up_after_two_failures(memory, fake_llm):
    fake_llm.replies = ["nope", "nope"]
    agent = Agent("ana", "imp", "strategist", memory)
    with pytest.raises(ValueError, match="Pas de JSON valide"):
        asyncio.run(agent.night_action(["bruno", "carla"]))


def test_night_action_without_options_raises(memory, fake_llm):
    agent = Agent("ana", "imp", "strategist", memory)
    with pytest.raises(ValueError, match="Aucune option"):
        asyncio.run(agent.night_action([]))
    assert fake_llm.calls == []  # aucun appel inutile


def test_psychic_chooses_two_targets(memory, fake_llm):
    fake_llm.replies = ['{"cibles": ["ana", "bruno"], "raison": "x"}']
    agent = Agent("carla", "psychic", "paranoid", memory)
    assert asyncio.run(agent.night_action(["ana", "bruno", "carla"], number_of_targets=2)) == ["ana", "bruno"]


def test_nominate_nobody_returns_none(memory, fake_llm):
    fake_llm.replies = ['{"cible": "personne", "raison": "x"}']
    agent = Agent("ana", "monk", "observer", memory)
    assert asyncio.run(agent.nominate(["bruno", "carla"])) is None


def test_nominate_player(memory, fake_llm):
    fake_llm.replies = ['{"cible": "carla", "raison": "x"}']
    agent = Agent("ana", "monk", "observer", memory)
    assert asyncio.run(agent.nominate(["bruno", "carla"])) == "carla"


def test_vote(memory, fake_llm):
    fake_llm.replies = ['{"vote": false, "raison": "x"}']
    agent = Agent("ana", "monk", "observer", memory)
    assert asyncio.run(agent.vote("bruno")) is False


def test_speak_private_mentions_partners(memory, fake_llm):
    fake_llm.replies = ["Salut !"]
    agent = Agent("ana", "monk", "observer", memory)
    assert asyncio.run(agent.speak_private(["bruno"])) == "Salut !"
    assert "conversation privée avec bruno" in fake_llm.calls[0][-1]["content"]


# --- create_agents ----------------------------------------------------------

def test_create_agents_skips_human(memory):
    agents = create_agents(
        {"ana": ("imp", "clown"), "bruno": ("monk", "observer"), "carla": ("psychic", "paranoid")},
        memory,
        human_id="carla",
    )
    assert sorted(agents) == ["ana", "bruno"]
    assert agents["ana"].role == "imp"


def test_create_agents_requires_human_in_assignments(memory):
    with pytest.raises(ValueError):
        create_agents({"ana": ("imp", "clown")}, memory, human_id="carla")
