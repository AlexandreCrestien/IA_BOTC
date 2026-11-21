"""Partie complète jouée de bout en bout par scripts/check_full_game.py (front simulé <-> vrai serveur <-> moteur),
en mode simulation : aucun appel LLM. Plusieurs centaines de vérifications par partie."""
import importlib.util
from pathlib import Path

import pytest

from backend.ai import llm_client
from backend.server import game_runner

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_full_game.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_full_game", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def simulated_llm(monkeypatch, clean_server):
    """Mode simulation pour ce test seulement (le script l'active normalement avant l'import de llm_client)."""
    monkeypatch.setenv("SIMULATE_LLM", "1")
    monkeypatch.setattr(llm_client, "SIMULATE_LLM", True)
    monkeypatch.setattr(llm_client, "CALL_PAUSE_SECONDS", 0)
    monkeypatch.setattr(llm_client.router, "acompletion", llm_client._simulated_acompletion)
    monkeypatch.setitem(game_runner.GAME_CONFIG, "seed", None)


# 1 : Veilleur ; 3 : Faucheur (partie courte) ; 5 : Apothicaire, partie longue
@pytest.mark.parametrize("seed", [1, 3, 5])
def test_full_game(simulated_llm, seed):
    script = load_script()
    game, report, _ = script.run(seed)
    assert report.failed == [], "\n".join(report.failed)
    assert game.game_over is not None
    assert report.passed > 100
