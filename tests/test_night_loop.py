import pytest
import random

from backend.game_engine import collect_night_choices, play_night
from backend.models import GameState, Phase, Player
from backend.rules import get_role, legal_actions


def make_player(id: str, role: str) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role))


def night_game() -> GameState:
    players = (
        make_player("a", "imp"),
        make_player("b", "poisoner"),
        make_player("c", "monk"),
        make_player("d", "psychic"),
        make_player("e", "detective"),
        make_player("f", "butler"),
    )
    return GameState(turn=2, phase=Phase.NUIT, players=players, channels=(), log=())


def first_legal_choice(state: GameState, player_id: str) -> tuple[str, ...]:
    legal = legal_actions(state, player_id)
    return legal.targets[: legal.count]


def test_random_choices_are_all_valid():
    state = night_game()
    choices = collect_night_choices(state, random.Random(3))
    for player_id, choice in choices.items():
        legal = legal_actions(state, player_id)
        assert len(choice) == legal.count
        assert all(target in legal.targets for target in choice)


def test_hook_choice_is_used():
    state = night_game()
    choices = collect_night_choices(state, random.Random(3), choose=first_legal_choice)
    assert choices["a"] == ("b",)


def test_invalid_hook_choice_falls_back_to_random():
    state = night_game()
    choices = collect_night_choices(state, random.Random(3), choose=lambda s, pid: ("zz",))
    for player_id, choice in choices.items():
        legal = legal_actions(state, player_id)
        assert all(target in legal.targets for target in choice)


def test_play_night_returns_state_and_choices():
    state = night_game()
    new_state, choices = play_night(state, random.Random(3), choose=first_legal_choice)
    assert choices["a"] == ("b",)
    assert new_state.phase == Phase.NUIT


def test_same_seed_same_choices():
    first = collect_night_choices(night_game(), random.Random(9))
    second = collect_night_choices(night_game(), random.Random(9))
    assert first == second

# --- Cibles vivantes seulement pour le Moine et l'Empoisonneur ---------------------

from backend.rules import legal_actions  # noqa: E402


def _game_with_dead_dan():
    from backend.models import GameState, Phase, Player
    from backend.rules import get_role
    roles = {"a": "imp", "b": "poisoner", "c": "monk", "d": "psychic", "e": "detective", "f": "butler"}
    players = tuple(Player(id=pid, name=pid.upper(), role=get_role(role)) for pid, role in roles.items())
    state = GameState(turn=2, phase=Phase.NUIT, players=players, channels=())
    return state.replace_player(state.player("d").die())


@pytest.mark.parametrize("role_id", ["c", "b"])  # Moine, Empoisonneur
def test_monk_and_poisoner_cannot_target_the_dead(role_id):
    assert "d" not in legal_actions(_game_with_dead_dan(), role_id).targets


@pytest.mark.parametrize("role_id", ["a", "f"])  # Diablotin, Majordome
def test_imp_and_butler_can_target_the_dead(role_id):
    assert "d" in legal_actions(_game_with_dead_dan(), role_id).targets
