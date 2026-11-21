"""Choix de repli : cibles tirées au hasard parmi les choix légaux (choix de nuit absent ou invalide)."""
import random

from backend.models import GameState, Phase, Player
from backend.rules import get_role, legal_actions, random_legal_choice


def make_player(id: str, role: str) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role))


def night_game(turn: int = 1) -> GameState:
    return GameState(
        turn=turn,
        phase=Phase.NIGHT,
        players=(
            make_player("a", "reaper"),
            make_player("b", "apothecary"),
            make_player("c", "watchman"),
            make_player("d", "medium"),
            make_player("e", "inquisitor"),
            make_player("f", "valet"),
        ),
    )


def test_random_choice_is_legal_and_has_right_size():
    state = night_game()
    targets = set(legal_actions(state, "d").targets)
    for seed in range(20):
        choice = random_legal_choice(state, "d", random.Random(seed))
        assert len(choice) == 2
        assert len(set(choice)) == 2
        assert set(choice) <= targets


def test_random_choice_empty_without_legal_target():
    state = night_game().model_copy(update={"phase": Phase.DISCUSSION})
    assert random_legal_choice(state, "b", random.Random(1)) == ()
