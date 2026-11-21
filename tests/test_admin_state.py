"""Route d'administration : état complet de la partie en cours (rien n'est caché)."""
import random

import pytest

from backend.game_engine import record_night_choices, setup_game
from backend.human_port import QueueHumanPort
from backend.models import EventType
from backend.server import admin, game_runner
from backend.server import websockets as ws

NAMES = {"h": "Alex", "p1": "marIA", "p2": "tobIAs", "p3": "mAIsie", "p4": "adrIAn", "p5": "dIAne"}
PERSONALITIES = ["agitator", "clown", "observer", "paranoid", "strategist"]


@pytest.fixture
def game(monkeypatch):
    """Partie mise en place par le vrai moteur (sans appel LLM), reliée au serveur comme par game_runner."""
    state, agents, memory = setup_game(NAMES, "h", PERSONALITIES, random.Random(0))
    port = QueueHumanPort()
    port.state, port.memory, port.agents = state, memory, agents
    monkeypatch.setattr(game_runner, "_current_human", "h")
    monkeypatch.setattr(game_runner, "_game_running", lambda: True)
    monkeypatch.setitem(ws.ports, "h", port)
    yield state, memory
    for store in (ws.night_log, ws.vote_log, ws.opened_channels):
        store.pop("h", None)


def test_sans_partie(monkeypatch):
    monkeypatch.setattr(game_runner, "_current_human", None)
    view = admin.build_debug_state()
    assert view["game_in_progress"] is False
    assert view["message"] == "Aucune partie n'a encore été lancée."


def test_joueurs_avec_role_camp_et_personnalite(game):
    state, _ = game
    view = admin.build_debug_state()

    assert view["status"] == "en cours"
    assert view["human"] == "Alex"
    assert len(view["players"]) == 6
    by_name = {p["name"]: p for p in view["players"]}
    for player in state.players:
        assert by_name[player.name]["role"] == player.role.name_FR  # rôles réels, rien de caché
    assert by_name["Alex"]["is_human"] is True and by_name["Alex"]["personality"] is None
    # Personnalités internes : le nom du fichier skill (jamais montré au joueur)
    assert {by_name[n]["personality"] for n in ["marIA", "tobIAs", "mAIsie", "adrIAn", "dIAne"]} == set(PERSONALITIES)
    assert {p["team"] for p in view["players"]} >= {"Démon", "Sbire"}


def test_historique_personnel_de_chaque_agent(game):
    state, memory = game
    memory.add_public(EventType.public_message, "p1", "Bonjour le village.")
    view = admin.build_debug_state()

    assert set(view["agent_histories"]) == {"marIA", "tobIAs", "mAIsie", "adrIAn", "dIAne"}
    marIA = view["agent_histories"]["marIA"]
    assert {"role": "Nuit 1 · public · marIA", "content": "Bonjour le village."} in marIA
    assert view["public_history"][-1] == {"moment": "Nuit 1", "sender": "marIA", "content": "Bonjour le village."}


def test_actions_de_nuit_de_tous_les_joueurs(game):
    state, memory = game
    record_night_choices(state, {"p1": ("p2",), "h": ("p3",)}, memory)
    view = admin.build_debug_state()

    actions = {(a["player"], a["content"]) for a in view["night_actions"]}
    assert ("marIA", "Nuit 1 : tu as choisi tobIAs.") in actions
    assert ("Alex", "Nuit 1 : tu as choisi mAIsie.") in actions


def test_historiques_du_joueur(game):
    ws.night_log["h"] = [{"turn": 1, "type": "result", "info": "Personne n'est mort cette nuit."}]
    ws.vote_log["h"] = [{"turn": 1, "voter": "Alex", "target": None, "executed": None}]
    view = admin.build_debug_state()
    assert view["night_history"] == ws.night_log["h"]
    assert view["vote_history"] == ws.vote_log["h"]
