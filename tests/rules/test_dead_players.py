import random

import pytest

from backend.models import GameState, Player
from backend.models.enums import Phase
from backend.rules.actions import legal_actions
from backend.rules.night_effects import kill
from backend.rules.powers import psychic_answer
from backend.rules import get_role

IMP = get_role("imp")
PSYCHIC = get_role("psychic")
VILLAGER = get_role("detective")  # villageois sans action de nuit


def make_state(phase: Phase = Phase.NIGHT) -> GameState:
    """Un Diablotin vivant, un Villageois mort, un Villageois vivant, une Voyante vivante."""
    return GameState(
        turn=2,
        phase=phase,
        players=(
            Player(id="imp", name="Imp", role=IMP),
            Player(id="mort", name="Mort", role=VILLAGER, alive=False, ghost_vote=True),
            Player(id="vivant", name="Vivant", role=VILLAGER),
            Player(id="voyante", name="Voyante", role=PSYCHIC),
        ),
    )


def test_imp_can_target_a_dead_player():
    state = make_state()
    assert "mort" in legal_actions(state, "imp").targets


def test_killing_a_dead_player_does_nothing():
    state = make_state()
    assert kill(state, "imp", "mort") == state


def test_dead_player_has_no_power():
    state = make_state()
    state = state.replace_player(state.player("imp").die())
    assert legal_actions(state, "imp").targets == ()


def test_psychic_can_probe_a_dead_demon():
    state = make_state()
    demon_mort = Player(id="demon_mort", name="DemonMort", role=IMP, alive=False, ghost_vote=True)
    state = state.model_copy(update={"players": state.players + (demon_mort,)})
    assert psychic_answer(state, "voyante", ("demon_mort",), random.Random(0)) is True


def test_psychic_probes_a_dead_non_demon():
    state = make_state()
    assert psychic_answer(state, "voyante", ("mort",), random.Random(0)) is False


def test_kill_during_the_day_raises():
    state = make_state(phase=Phase.DISCUSSION)
    with pytest.raises(ValueError):
        kill(state, "imp", "vivant")