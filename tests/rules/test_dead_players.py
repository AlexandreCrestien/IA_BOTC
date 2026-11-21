import random

import pytest

from backend.models import GameState, Player
from backend.models.enums import Phase
from backend.rules.actions import legal_actions
from backend.rules.night_effects import kill
from backend.rules.powers import medium_answer
from backend.rules import get_role

REAPER = get_role("reaper")
MEDIUM = get_role("medium")
VILLAGER = get_role("inquisitor")  # villageois sans action de nuit


def make_state(phase: Phase = Phase.NIGHT) -> GameState:
    """Un Faucheur vivant, un Villageois mort, un Villageois vivant, un Médium vivante."""
    return GameState(
        turn=2,
        phase=phase,
        players=(
            Player(id="imp", name="Imp", role=REAPER),
            Player(id="mort", name="Mort", role=VILLAGER, alive=False, ghost_vote=True),
            Player(id="vivant", name="Vivant", role=VILLAGER),
            Player(id="voyante", name="Médium", role=MEDIUM),
        ),
    )


def test_reaper_can_target_a_dead_player():
    state = make_state()
    assert "mort" in legal_actions(state, "imp").targets


def test_killing_a_dead_player_does_nothing():
    state = make_state()
    assert kill(state, "imp", "mort") == state


def test_dead_player_has_no_power():
    state = make_state()
    state = state.replace_player(state.player("imp").die())
    assert legal_actions(state, "imp").targets == ()


def test_medium_can_probe_a_dead_demon():
    state = make_state()
    demon_mort = Player(id="demon_mort", name="DemonMort", role=REAPER, alive=False, ghost_vote=True)
    state = state.model_copy(update={"players": state.players + (demon_mort,)})
    assert medium_answer(state, "voyante", ("demon_mort",), random.Random(0)) is True


def test_medium_probes_a_dead_non_demon():
    state = make_state()
    assert medium_answer(state, "voyante", ("mort",), random.Random(0)) is False


def test_kill_during_the_day_raises():
    state = make_state(phase=Phase.DISCUSSION)
    with pytest.raises(ValueError):
        kill(state, "imp", "vivant")