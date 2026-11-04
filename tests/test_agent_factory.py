from unittest.mock import MagicMock
import pytest

from backend.models import Role, Joueur, Equipe, Phase
from backend.prompt_loader import PromptLoader
from backend.agent_factory import Agent, AgentFactory, create_all_agents
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
    return memory


@pytest.fixture
def sample_role_data():
    """Données valides pour un rôle."""
    return {
        "nom": "Moine",
        "nom_EN": "monk",
        "camp": Equipe.VILLAGEOIS,
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
    player = Joueur(id="j1", nom="mAIsie", role=role)
    
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
        "nom": "Moine",
        "nom_EN": "monk",
        "camp": Equipe.VILLAGEOIS,
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
    assert "Alice" in agent.system_prompt
    assert "moine" in agent.system_prompt.lower() or "monk" in agent.system_prompt.lower()
