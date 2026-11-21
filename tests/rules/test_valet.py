import pytest

from backend.models import Effect, GameState, Phase, Player, EffectType
from backend.rules import choose_master, get_role, master_of, resolve_night, resolve_vote, vote_result


def make_player(id: str, role: str, **kwargs) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role), **kwargs)


def night_game(valet: Player | None = None) -> GameState:
    players = (
        make_player("a", "reaper"),
        make_player("b", "apothecary"),
        make_player("c", "watchman"),
        make_player("d", "medium"),
        make_player("e", "inquisitor"),
        valet or make_player("f", "valet"),
    )
    return GameState(turn=1, phase=Phase.NIGHT, players=players)


def vote_game(valet: Player) -> GameState:
    players = (
        make_player("a", "reaper"),
        make_player("b", "apothecary"),
        make_player("c", "watchman"),
        make_player("d", "medium"),
        make_player("e", "inquisitor"),
        valet,
    )
    return GameState(turn=1, phase=Phase.VOTE, players=players)


def test_choose_master_sets_link():
    state = choose_master(night_game(), "f", "a")
    assert master_of(state, "f") == "a"


def test_valet_cannot_choose_himself():
    with pytest.raises(ValueError):
        choose_master(night_game(), "f", "f")


def test_choice_replaces_previous_master():
    state = choose_master(night_game(), "f", "a")
    state = choose_master(state, "f", "b")
    assert master_of(state, "f") == "b"


def test_poisoned_valet_sets_nothing():
    effect = Effect(type=EffectType.POISONED, source="apothecary", turn_start=1, phase_start=Phase.NIGHT)
    valet = make_player("f", "valet", effects=(effect,))
    state = choose_master(night_game(valet), "f", "a")
    assert master_of(state, "f") is None


def test_resolve_night_sets_master():
    state = resolve_night(night_game(), {"f": ("a",)})
    assert master_of(state, "f") == "a"


def test_valet_vote_ignored_if_master_does_not_vote():
    valet = make_player("f", "valet", links={"master": "a"})
    state = vote_game(valet)
    # Sans le filtre, c serait exécuté avec 2 votes sur 3.
    votes = {"b": "c", "d": "e", "f": "c"}
    assert vote_result(state, votes) is None
    assert resolve_vote(state, votes).player("c").alive


def test_valet_vote_counts_if_master_votes():
    valet = make_player("f", "valet", links={"master": "a"})
    state = vote_game(valet)
    votes = {"a": "d", "b": "c", "f": "c"}
    assert vote_result(state, votes) == "c"


def test_valet_without_master_votes_freely():
    state = vote_game(make_player("f", "valet"))
    votes = {"b": "c", "f": "c"}
    assert vote_result(state, votes) == "c"


def test_poisoned_valet_votes_even_if_master_does_not_vote():
    effect = Effect(type=EffectType.POISONED, source="apothecary", turn_start=1, phase_start=Phase.NIGHT)
    valet = make_player("f", "valet", effects=(effect,), links={"master": "a"})
    state = vote_game(valet)
    votes = {"b": "c", "f": "c"}
    assert vote_result(state, votes) == "c"