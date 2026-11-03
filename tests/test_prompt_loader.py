import pytest
from pathlib import Path
from prompt_loader import PromptLoader

@pytest.fixture
def fake_skills_dir(tmp_path):
    """
    Fixture qui crée une structure temporaire de dossiers 'skills' 
    avec des fichiers Markdown de test.
    """
    skills_dir = tmp_path / "skills"
    roles_dir = skills_dir / "roles"
    personalities_dir = skills_dir / "personalities"

    roles_dir.mkdir(parents=True)
    personalities_dir.mkdir(parents=True)

    # Fichiers de test
    (skills_dir / "general_rules.md").write_text("RÈGLES GLOBALES DE TEST", encoding="utf-8")
    (roles_dir / "monk.md").write_text("MÉCANIQUE DU MOINE", encoding="utf-8")
    (personalities_dir / "parano.md").write_text("STYLE PARANOÏAQUE", encoding="utf-8")

    return skills_dir

def test_assemble_system_prompt_success(fake_skills_dir):
    """Vérifie que l'assemblage complet se fait sans erreur avec tous les blocs requis."""
    loader = PromptLoader(base_dir=fake_skills_dir)
    agent_name = "TestBot"
    
    prompt = loader.assemble_system_prompt(
        role_name="monk", 
        personality_name="parano", 
        agent_name=agent_name
    )

    # Vérifications des présences dans le prompt généré
    assert agent_name in prompt
    assert "RÈGLES GLOBALES DE TEST" in prompt
    assert "MÉCANIQUE DU MOINE" in prompt
    assert "STYLE PARANOÏAQUE" in prompt
    assert "# CONTEXTE ET OBJECTIF" in prompt

def test_assemble_system_prompt_case_and_whitespace_insensitivity(fake_skills_dir):
    """Vérifie que la normalisation (lower + strip) fonctionne correctement."""
    loader = PromptLoader(base_dir=fake_skills_dir)
    
    # Passing mixed cases and extra whitespaces
    prompt = loader.assemble_system_prompt(
        role_name="  MoNk  ", 
        personality_name=" PaRaNo "
    )

    assert "MÉCANIQUE DU MOINE" in prompt
    assert "STYLE PARANOÏAQUE" in prompt

def test_missing_role_file_raises_error(fake_skills_dir):
    """Vérifie qu'une exception est levée si le fichier de rôle n'existe pas."""
    loader = PromptLoader(base_dir=fake_skills_dir)

    with pytest.raises(FileNotFoundError) as exc_info:
        loader.assemble_system_prompt(role_name="non_existent_role", personality_name="parano")
    
    assert "non_existent_role.md" in str(exc_info.value)

def test_missing_personality_file_raises_error(fake_skills_dir):
    """Vérifie qu'une exception est levée si le fichier de personnalité n'existe pas."""
    loader = PromptLoader(base_dir=fake_skills_dir)

    with pytest.raises(FileNotFoundError) as exc_info:
        loader.assemble_system_prompt(role_name="monk", personality_name="non_existent_personality")
    
    assert "non_existent_personality.md" in str(exc_info.value)

def test_missing_general_rules_file_raises_error(tmp_path):
    """Vérifie qu'une exception est levée si general_rules.md est absent."""
    skills_dir = tmp_path / "skills"
    (skills_dir / "roles").mkdir(parents=True)
    (skills_dir / "personalities").mkdir(parents=True)

    (skills_dir / "roles" / "monk.md").write_text("Rôle", encoding="utf-8")
    (skills_dir / "personalities" / "parano.md").write_text("Perso", encoding="utf-8")
    # general_rules.md n'est délibérément pas créé

    loader = PromptLoader(base_dir=skills_dir)

    with pytest.raises(FileNotFoundError) as exc_info:
        loader.assemble_system_prompt(role_name="monk", personality_name="parano")
    
    assert "general_rules.md" in str(exc_info.value)