import random

import pytest

from backend.models import GameState, Player
from backend.models.enums import Equipe, Phase
from backend.models.role import Role
from backend.rules.actions import legal_actions
from backend.rules.night_effects import kill
from backend.rules.powers import psychic_answer

IMP = Role(name_FR="Diablotin", name_EN="imp", team=Equipe.DEMON, phase=Phase.NUIT)
PSYCHIC = Role(name_FR="Voyante", name_EN="psychic", team=Equipe.VILLAGEOIS, phase=Phase.NUIT)
VILLAGER = Role(name_FR="Villageois", name_EN="villager", team=Equipe.VILLAGEOIS)


def make_state(phase: Phase = Phase.NUIT) -> GameState:
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


def test_le_diablotin_peut_cibler_un_mort():
    state = make_state()
    assert "mort" in legal_actions(state, "imp").targets


def test_tuer_un_mort_ne_fait_rien():
    state = make_state()
    assert kill(state, "imp", "mort") == state


def test_un_mort_n_a_plus_de_pouvoir():
    state = make_state()
    state = state.replace_player(state.player("imp").die())
    assert legal_actions(state, "imp").targets == ()


def test_la_voyante_peut_sonder_un_mort_demon():
    state = make_state()
    demon_mort = Player(id="demon_mort", name="DemonMort", role=IMP, alive=False, ghost_vote=True)
    state = state.model_copy(update={"players": state.players + (demon_mort,)})
    assert psychic_answer(state, "voyante", ("demon_mort",), random.Random(0)) is True


def test_la_voyante_sonde_un_mort_non_demon():
    state = make_state()
    assert psychic_answer(state, "voyante", ("mort",), random.Random(0)) is False


def test_kill_pendant_le_jour_leve_une_erreur():
    state = make_state(phase=Phase.DISCUSSION)
    with pytest.raises(ValueError):
        kill(state, "imp", "vivant")