import pytest
from backend.models import Role, Joueur, Equipe, Phase
from backend.prompt_loader import PromptLoader
from backend.agent_factory import AgentFactory, LLMAgent


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


def test_llm_agent_properties(sample_role_data):
    """Vérifie que les propriétés de LLMAgent restituent correctement les infos."""
    role = Role(**sample_role_data)
    player = Joueur(id="j1", nom="IAn", role=role)
    
    agent = LLMAgent(
        player=player,
        personality="Paranoïaque",
        system_prompt="Prompt système de test"
    )

    assert agent.name == "IAn"
    assert agent.role_name == "Moine"
    assert agent.personality == "Paranoïaque"
    assert agent.system_prompt == "Prompt système de test"


def test_agent_factory_creates_agent_successfully(fake_skills_env, sample_role_data, sample_personality_data):
    """Vérifie que l'AgentFactory assemble parfaitement le tout en utilisant les attributs EN."""
    loader = PromptLoader(base_dir=fake_skills_env)
    factory = AgentFactory(prompt_loader=loader)

    agent = factory.create_agent(
        agent_id="agent_1",
        agent_name="mAIsie",
        role_data=sample_role_data,
        personality_data=sample_personality_data
    )

    assert isinstance(agent, LLMAgent)
    assert agent.name == "mAIsie"
    assert agent.role_name == "Moine"
    assert agent.personality == "Paranoïaque"

    assert "mAIsie" in agent.system_prompt
    assert "Règles générales" in agent.system_prompt
    assert "Description du rôle Monk" in agent.system_prompt
    assert "Personnalité Parano" in agent.system_prompt


def test_agent_factory_personality_fallback(fake_skills_env, sample_role_data):
    """Vérifie que si le nom FR est absent de personality_data, on retombe proprement sur le nom EN."""
    loader = PromptLoader(base_dir=fake_skills_env)
    factory = AgentFactory(prompt_loader=loader)

    minimal_personality_data = {
        "personality_name_EN": "paranoid"
    }

    agent = factory.create_agent(
        agent_id="agent_2",
        agent_name="lIAm",
        role_data=sample_role_data,
        personality_data=minimal_personality_data
    )

    assert agent.personality == "paranoid"


# TEST D'INTÉGRATION

def test_agent_factory_real_integration():
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
        agent_name="adrIAn",
        role_data=role_data,
        personality_data=personality_data
    )

    assert isinstance(agent, LLMAgent)
    assert isinstance(agent.player, object)
    assert agent.name == "adrIAn"
    assert agent.role_name == "Moine"
    assert agent.personality == "Paranoïaque"

    assert len(agent.system_prompt) > 0
    assert "adrIAn" in agent.system_prompt
    assert "moine" in agent.system_prompt.lower() or "monk" in agent.system_prompt.lower()