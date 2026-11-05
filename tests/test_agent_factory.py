import asyncio
from unittest.mock import MagicMock

import pytest

import backend.agent_factory as agent_factory
import backend.llm_client as llm_client

from backend.models import Role, Player, Equipe, Phase
from backend.prompt_loader import PromptLoader
from backend.agent_factory import NOBODY, PASS, Agent, AgentFactory, create_all_agents
from backend.memory_manager import MemoryManager


@pytest.fixture
def fake_skills_env(tmp_path):
    """
    Crée un environnement de skills factice isolé pour tester la factory sans toucher aux fichiers.
    """
    skills_dir = tmp_path / "skills"
    roles_dir = skills_dir / "roles"
    personalities_dir = skills_dir / "personalities"

    roles_dir.mkdir(parents=True)
    personalities_dir.mkdir(parents=True)

    (skills_dir / "general_rules.md").write_text("Règles générales et consignes de sécurité", encoding="utf-8")
    (roles_dir / "monk.md").write_text("Description du rôle Monk : protège un joueur.", encoding="utf-8")
    (personalities_dir / "paranoid.md").write_text("Personnalité Parano : tu te méfies de tout le monde.", encoding="utf-8")

    return skills_dir


@pytest.fixture
def mock_memory():
    """Mock du MemoryManager pour fournir les joueurs et le contexte."""
    memory = MagicMock(spec=MemoryManager)
    memory.player_ids = {"agent_1", "agent_2", "human_id"}
    memory.context_for.return_value = "Historique fictif de la partie."
    memory.name_of.side_effect = lambda player_id: player_id
    return memory


@pytest.fixture
def sample_role_data():
    """Données valides pour un rôle."""
    return {
        "name_FR": "Moine",
        "name_EN": "monk",
        "team": Equipe.VILLAGEOIS,
        "phase": Phase.NUIT,
        "description": "Un protecteur nocturne."
    }

@pytest.fixture
def sample_personality_data():
    """Données de personnalité : noms français et anglais."""
    return {
        "personality_name_FR": "Paranoïaque",
        "personality_name_EN": "paranoid"
    }


def test_agent_properties(sample_role_data, mock_memory):
    """Vérifie que les propriétés de l'Agent restituent correctement les infos."""
    role = Role(**sample_role_data)
    player = Player(id="j1", name="mAIsie", role=role)
    
    agent = Agent(
        player=player,
        personality="Paranoïaque",
        memory=mock_memory,
        system_prompt="Prompt système de test"
    )

    assert agent.player_id == "j1"
    assert agent.name == "mAIsie"
    assert agent.role_name == "Moine"
    assert agent.personality == "Paranoïaque"
    assert "agent_1" in agent._build_system_prompt()


def test_agent_factory_creates_agent_successfully(fake_skills_env, sample_role_data, sample_personality_data, mock_memory):
    """Vérifie que l'AgentFactory assemble parfaitement le tout."""
    loader = PromptLoader(base_dir=fake_skills_env)
    factory = AgentFactory(prompt_loader=loader)

    agent = factory.create_agent(
        agent_id="agent_1",
        agent_name="IAn",
        role_data=sample_role_data,
        personality_data=sample_personality_data,
        memory=mock_memory
    )

    assert isinstance(agent, Agent)
    assert agent.name == "IAn"
    assert agent.role_name == "Moine"
    assert agent.personality == "Paranoïaque"
    assert agent.personality_key == "paranoid"

    assert "IAn" in agent.system_prompt
    assert "Règles générales" in agent.system_prompt
    assert "Description du rôle Monk" in agent.system_prompt
    assert "Personnalité Parano" in agent.system_prompt


def test_agent_factory_personality_fallback(fake_skills_env, sample_role_data, mock_memory):
    """Vérifie que si le nom FR est absent de personality_data, on retombe proprement sur le nom EN."""
    loader = PromptLoader(base_dir=fake_skills_env)
    factory = AgentFactory(prompt_loader=loader)

    minimal_personality_data = {
        "personality_name_EN": "paranoid"
    }

    agent = factory.create_agent(
        agent_id="agent_2",
        agent_name="Charlie",
        role_data=sample_role_data,
        personality_data=minimal_personality_data,
        memory=mock_memory
    )

    assert agent.personality == "paranoid"


def test_create_all_agents_excludes_human(fake_skills_env, sample_role_data, sample_personality_data, mock_memory):
    """Vérifie que create_all_agents génère les bons agents IA tout en excluant le joueur humain."""
    loader = PromptLoader(base_dir=fake_skills_env)
    
    assignments = {
        "human_id": ("Humain", sample_role_data, sample_personality_data),
        "agent_1": ("IAn", sample_role_data, sample_personality_data),
        "agent_2": ("dIAna", sample_role_data, sample_personality_data)
    }

    agents = create_all_agents(
        assignments=assignments,
        memory=mock_memory,
        human_id="human_id",
        prompt_loader=loader
    )

    assert "human_id" not in agents
    assert "agent_1" in agents
    assert "agent_2" in agents
    assert isinstance(agents["agent_1"], Agent)
    assert agents["agent_1"].name == "IAn"


# TEST D'INTÉGRATION

def test_agent_factory_real_integration(mock_memory):
    """
    Test d'intégration réel : vérifie que l'AgentFactory fonctionne avec le vrai PromptLoader (pointant sur le vrai dossier /skills) et valide les vrais objets Pydantic.
    """
    factory = AgentFactory()

    role_data = {
        "name_FR": "Moine",
        "name_EN": "monk",
        "team": Equipe.VILLAGEOIS,
        "phase": Phase.NUIT,
        "description": "Protection nocturne."
    }

    personality_data = {
        "personality_name_FR": "Paranoïaque",
        "personality_name_EN": "paranoid"
    }

    agent = factory.create_agent(
        agent_id="player_01",
        agent_name="dIAna",
        role_data=role_data,
        personality_data=personality_data,
        memory=mock_memory
    )

    assert isinstance(agent, Agent)
    assert isinstance(agent.player, object)
    assert agent.name == "dIAna"
    assert agent.role_name == "Moine"
    assert agent.personality == "Paranoïaque"

    assert len(agent.system_prompt) > 0
    assert "dIAna" in agent.system_prompt
    assert "moine" in agent.system_prompt.lower() or "monk" in agent.system_prompt.lower()

# --- Actions de l'agent avec un faux LLM ------------------------------------

@pytest.fixture
def fake_llm(monkeypatch):
    """Remplace le LLM par des réponses préparées, renvoyées dans l'ordre. Aucun appel réseau.
    fake_llm.calls : les messages reçus à chaque appel."""
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


@pytest.fixture
def agent(sample_role_data):
    memory = MemoryManager(["ana", "bruno", "carla"])
    player = Player(id="ana", name="ana", role=Role(**sample_role_data))
    return Agent(player=player, personality="Provocateur", memory=memory, system_prompt="prompt",
                 personality_key="agitator")


def test_night_action_returns_legal_target(agent, fake_llm):
    fake_llm.replies = ['{"cibles": ["bruno"], "raison": "x"}']
    assert asyncio.run(agent.night_action(["bruno", "carla"])) == ["bruno"]


def test_night_action_instruction_shows_json_example(agent, fake_llm):
    """Régression : les accolades de l'exemple JSON faisaient planter la f-string."""
    fake_llm.replies = ['{"cibles": ["bruno"], "raison": "x"}']
    asyncio.run(agent.night_action(["bruno", "carla"]))
    assert '{"cibles": ["nom", ...]' in fake_llm.calls[0][-1]["content"]


def test_night_action_retries_after_illegal_target(agent, fake_llm):
    fake_llm.replies = ['{"cibles": ["zoe"], "raison": "x"}', '{"cibles": ["carla"], "raison": "x"}']
    assert asyncio.run(agent.night_action(["bruno", "carla"])) == ["carla"]
    assert "n'est pas un choix possible" in fake_llm.calls[1][-1]["content"]


def test_night_action_retries_after_wrong_number_of_targets(agent, fake_llm):
    fake_llm.replies = ['{"cibles": ["bruno"], "raison": "x"}', '{"cibles": ["bruno", "carla"], "raison": "x"}']
    assert asyncio.run(agent.night_action(["bruno", "carla"], number_of_targets=2)) == ["bruno", "carla"]
    assert "exactement 2" in fake_llm.calls[1][-1]["content"]


def test_night_action_gives_up_after_two_failures(agent, fake_llm):
    fake_llm.replies = ["nope", "nope"]
    with pytest.raises(ValueError, match="Pas de JSON valide"):
        asyncio.run(agent.night_action(["bruno", "carla"]))


def test_night_action_without_options_raises(agent, fake_llm):
    with pytest.raises(ValueError, match="Aucune option"):
        asyncio.run(agent.night_action([]))
    assert fake_llm.calls == []  # aucun appel inutile


def test_vote_for_player(agent, fake_llm):
    fake_llm.replies = ['{"cible": "carla", "raison": "x"}']
    assert asyncio.run(agent.vote(["bruno", "carla"])) == "carla"
    assert '{"cible": "nom"' in fake_llm.calls[0][-1]["content"]


def test_vote_for_nobody_returns_none(agent, fake_llm):
    fake_llm.replies = [f'{{"cible": "{NOBODY}", "raison": "x"}}']
    assert asyncio.run(agent.vote(["bruno", "carla"])) is None


def test_vote_retries_after_illegal_target(agent, fake_llm):
    fake_llm.replies = ['{"cible": "zoe", "raison": "x"}', '{"cible": "bruno", "raison": "x"}']
    assert asyncio.run(agent.vote(["bruno", "carla"])) == "bruno"


@pytest.mark.parametrize("reply", [PASS, "passe", "PASSE.", "  Passe  ", "**PASSE**", "« Passe »", "Passe !"])
def test_optional_speaker_can_pass(agent, fake_llm, reply):
    fake_llm.replies = [reply]
    assert asyncio.run(agent.speak_public(optional=True)) is None
    assert PASS in fake_llm.calls[0][-1]["content"]


def test_obliged_speaker_is_not_offered_to_pass(agent, fake_llm):
    fake_llm.replies = ["Je soupçonne bruno."]
    assert asyncio.run(agent.speak_public()) == "Je soupçonne bruno."
    assert PASS not in fake_llm.calls[0][-1]["content"]


def test_optional_speaker_message_is_kept(agent, fake_llm):
    fake_llm.replies = ["Je passe mon tour de garde, mais bruno ment."]
    assert asyncio.run(agent.speak_public(optional=True)) == "Je passe mon tour de garde, mais bruno ment."


def test_speak_private_mentions_partners(agent, fake_llm):
    fake_llm.replies = ["Salut !"]
    assert asyncio.run(agent.speak_private(["bruno"])) == "Salut !"
    assert "conversation privée avec bruno" in fake_llm.calls[0][-1]["content"]


def test_personality_key_defaults_to_personality(sample_role_data, mock_memory):
    player = Player(id="j1", name="j1", role=Role(**sample_role_data))
    agent = Agent(player=player, personality="paranoid", memory=mock_memory, system_prompt="x")
    assert agent.personality_key == "paranoid"


def test_create_all_agents_requires_human(fake_skills_env, sample_role_data, sample_personality_data, mock_memory):
    with pytest.raises(ValueError, match="humain"):
        create_all_agents({"agent_1": ("IAn", sample_role_data, sample_personality_data)},
                          mock_memory, human_id="human_id",
                          prompt_loader=PromptLoader(base_dir=fake_skills_env))


# --- Noms affichés dans les prompts ------------------------------------------------

@pytest.fixture
def named_agent(sample_role_data):
    memory = MemoryManager({"p1": "Ana", "p2": "Bruno", "p3": "Carla"})
    player = Player(id="p1", name="Ana", role=Role(**sample_role_data))
    return Agent(player=player, personality="Provocateur", memory=memory, system_prompt="prompt",
                 personality_key="agitator")


def test_system_prompt_lists_player_names(named_agent, fake_llm):
    fake_llm.replies = ["Salut."]
    asyncio.run(named_agent.speak_public())
    system = fake_llm.calls[0][0]["content"]
    assert "Joueurs présents dans la partie : Ana, Bruno, Carla." in system
    assert "p2" not in system


def test_speak_private_uses_partner_names(named_agent, fake_llm):
    fake_llm.replies = ["Salut !"]
    asyncio.run(named_agent.speak_private(["p2", "p3"]))
    assert "conversation privée avec Bruno, Carla" in fake_llm.calls[0][-1]["content"]


def test_optional_instruction_says_passing_is_normal(agent, fake_llm):
    fake_llm.replies = [PASS]
    asyncio.run(agent.speak_public(optional=True))
    assert "passer ton tour est un choix normal" in fake_llm.calls[0][-1]["content"]


def test_long_message_starting_with_passe_is_kept(agent, fake_llm):
    fake_llm.replies = ["Passe-moi le relais : bruno ment."]
    assert asyncio.run(agent.speak_public(optional=True)) == "Passe-moi le relais : bruno ment."
