import pytest
from pathlib import Path
from backend.prompt_loader import PromptLoader


# --- TESTS DU FONCTIONNEMENT GLOBAL SUR DES FICHIERS MOCKS ---


@pytest.fixture
def fake_skills_dir(tmp_path):
    """
    Fixture qui crée une structure temporaire de dossiers 'skills' avec des fichiers Markdown de test.
    """
    skills_dir = tmp_path / "skills"
    roles_dir = skills_dir / "roles"
    personalities_dir = skills_dir / "personalities"

    roles_dir.mkdir(parents=True)
    personalities_dir.mkdir(parents=True)

    (skills_dir / "general_rules.md").write_text("RÈGLES GLOBALES DE TEST", encoding="utf-8")
    (roles_dir / "monk.md").write_text("RÔLE DU MOINE", encoding="utf-8")
    (personalities_dir / "parano.md").write_text("STYLE PARANO", encoding="utf-8")

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

    assert agent_name in prompt
    assert "RÈGLES GLOBALES DE TEST" in prompt
    assert "RÔLE DU MOINE" in prompt
    assert "STYLE PARANO" in prompt
    assert "# CONTEXTE ET OBJECTIF" in prompt


def test_assemble_system_prompt_case_and_whitespace_insensitivity(fake_skills_dir):
    """Vérifie que la normalisation (lower + strip) fonctionne correctement."""
    loader = PromptLoader(base_dir=fake_skills_dir)

    prompt = loader.assemble_system_prompt(
        role_name="  MoNk  ", 
        personality_name=" PaRaNo "
    )

    assert "RÔLE DU MOINE" in prompt
    assert "STYLE PARANO" in prompt


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


# --- TESTS D'INTÉGRATION DYNAMIQUES SUR LES VRAIS FICHIERS ---

def get_all_roles():
    """Récupère la liste de tous les noms de rôles."""
    roles_dir = Path("skills/roles")
    if not roles_dir.exists():
        return []
    return [f.stem for f in roles_dir.glob("*.md")]


def get_all_personalities():
    """Récupère la liste de tous les noms de personnalités."""
    pers_dir = Path("skills/personalities")
    if not pers_dir.exists():
        return []
    return [f.stem for f in pers_dir.glob("*.md")]


def test_general_rules_file_exists():
    """Vérifie que le fichier general_rules.md existe et n'est pas vide à la racine de 'skills'."""
    loader = PromptLoader()
    assert loader.general_rules_file.exists(), f"Introuvable : {loader.general_rules_file}"
    content = loader.general_rules_file.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "Le fichier general_rules.md est vide."


@pytest.mark.parametrize("role_name", get_all_roles())
def test_every_real_role_loads_correctly(role_name):
    """Test unitaire paramétré : s'assure que chaque fichier de rôle se charge sans erreur."""
    loader = PromptLoader()
    personalities = get_all_personalities()
    assert personalities, "Aucune personnalité trouvée pour effectuer le test."

    role_file_path = loader.roles_dir / f"{role_name}.md"
    expected_role_content = role_file_path.read_text(encoding="utf-8").strip()

    prompt = loader.assemble_system_prompt(role_name=role_name, personality_name=personalities[0])

    assert expected_role_content in prompt, (
        f"Le contenu du rôle '{role_name}' n'apparaît pas dans le system prompt assemblé."
    )


@pytest.mark.parametrize("personality_name", get_all_personalities())
def test_every_real_personality_loads_correctly(personality_name):
    """Test unitaire paramétré : s'assure que chaque fichier de personnalité se charge sans erreur."""
    loader = PromptLoader()
    roles = get_all_roles()
    assert roles, "Aucun rôle trouvé pour effectuer le test."

    pers_file_path = loader.personalities_dir / f"{personality_name}.md"
    expected_pers_content = pers_file_path.read_text(encoding="utf-8").strip()

    prompt = loader.assemble_system_prompt(role_name=roles[0], personality_name=personality_name)

    assert expected_pers_content in prompt, (
        f"Le contenu de la personnalité '{personality_name}' n'apparaît pas dans le system prompt assemblé."
    )

def test_personality_display_name_is_read_from_the_skill():
    from backend.prompt_loader import PromptLoader
    loader = PromptLoader()
    assert loader.personality_display_name("agitator") == "Provocateur"
    assert loader.personality_display_name("observer") == "Observateur"
    assert loader.personality_display_name("inconnue") == "inconnue"
