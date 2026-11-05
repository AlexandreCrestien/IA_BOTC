from backend.prompt_loader import PromptLoader
from backend.rules import SIX_PLAYER_ROLES


def test_every_role_has_a_skill_file():
    loader = PromptLoader()
    for role in SIX_PLAYER_ROLES:
        assert (loader.roles_dir / f"{role}.md").exists(), f"fiche manquante pour le rôle {role}"


def test_there_are_enough_personalities_for_ai_players():
    loader = PromptLoader()
    personalities = list(loader.personalities_dir.glob("*.md"))
    assert len(personalities) >= len(SIX_PLAYER_ROLES) - 1, "pas assez de personnalités pour les joueurs IA"