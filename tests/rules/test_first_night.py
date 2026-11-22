"""Informations de la première nuit : alliés du camp du mal, paire de l'Inquisiteur (fausse s'il est empoisonné)."""
import random

from backend.models import Effect, GameState, Phase, Player, EffectType
from backend.rules import first_night_info, get_role


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


def test_accomplice_learns_demon_and_demon_learns_accomplice():
    infos = first_night_info(night_game(), random.Random(1))
    assert ("b", "demon", ("a",)) in infos
    assert ("a", "accomplice", ("b",)) in infos


def test_inquisitor_sees_accomplice_among_two_players():
    for seed in range(20):
        infos = first_night_info(night_game(), random.Random(seed))
        pair = [i for i in infos if i.viewer_id == "e" and i.kind == "pair"]
        assert len(pair) == 1
        subjects = pair[0].subject_ids
        assert len(subjects) == 2
        assert "b" in subjects
        assert "e" not in subjects


def test_poisoned_inquisitor_gets_random_pair():
    poison = Effect(type=EffectType.POISONED, source="apothecary", turn_start=1, phase_start=Phase.NIGHT)
    state = night_game()
    state = state.model_copy(update={"players": tuple(
        p.add_effect(poison) if p.id == "e" else p for p in state.players
    )})
    seen_without_accomplice = False
    for seed in range(30):
        pair = [i for i in first_night_info(state, random.Random(seed))
                if i.viewer_id == "e" and i.kind == "pair"][0].subject_ids
        assert len(pair) == 2
        assert "e" not in pair
        if "b" not in pair:
            seen_without_accomplice = True
    assert seen_without_accomplice
