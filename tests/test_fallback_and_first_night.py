import random

from backend.models import Effect, GameState, Phase, Player, TypeEffet
from backend.rules import first_night_info, get_role, legal_actions, random_legal_choice


def make_player(id: str, role: str) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role))


def night_game(turn: int = 1) -> GameState:
    return GameState(
        turn=turn,
        phase=Phase.NUIT,
        players=(
            make_player("a", "imp"),
            make_player("b", "poisoner"),
            make_player("c", "monk"),
            make_player("d", "psychic"),
            make_player("e", "detective"),
            make_player("f", "butler"),
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


def test_minion_learns_demon_and_demon_learns_minion():
    infos = first_night_info(night_game(), random.Random(1))
    assert ("b", "demon", ("a",)) in infos
    assert ("a", "minion", ("b",)) in infos


def test_detective_sees_minion_among_two_players():
    for seed in range(20):
        infos = first_night_info(night_game(), random.Random(seed))
        pair = [i for i in infos if i.viewer_id == "e" and i.kind == "pair"]
        assert len(pair) == 1
        subjects = pair[0].subject_ids
        assert len(subjects) == 2
        assert "b" in subjects
        assert "e" not in subjects


def test_poisoned_detective_gets_random_pair():
    poison = Effect(type=TypeEffet.EMPOISONNE, source="poisoner", turn_start=1, phase_start=Phase.NUIT)
    state = night_game()
    state = state.model_copy(update={"players": tuple(
        p.add_effect(poison) if p.id == "e" else p for p in state.players
    )})
    seen_without_minion = False
    for seed in range(30):
        pair = [i for i in first_night_info(state, random.Random(seed))
                if i.viewer_id == "e" and i.kind == "pair"][0].subject_ids
        assert len(pair) == 2
        assert "e" not in pair
        if "b" not in pair:
            seen_without_minion = True
    assert seen_without_minion