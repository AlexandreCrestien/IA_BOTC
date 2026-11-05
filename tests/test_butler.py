import pytest

from backend.models import Effect, GameState, Phase, Player, TypeEffet
from backend.rules import choose_master, get_role, master_of, resolve_night, resolve_vote, vote_result


def make_player(id: str, role: str, **kwargs) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role), **kwargs)


def night_game(butler: Player | None = None) -> GameState:
    players = (
        make_player("a", "imp"),
        make_player("b", "poisoner"),
        make_player("c", "monk"),
        make_player("d", "psychic"),
        make_player("e", "detective"),
        butler or make_player("f", "butler"),
    )
    return GameState(turn=1, phase=Phase.NUIT, players=players)


def vote_game(butler: Player) -> GameState:
    players = (
        make_player("a", "imp"),
        make_player("b", "poisoner"),
        make_player("c", "monk"),
        make_player("d", "psychic"),
        make_player("e", "detective"),
        butler,
    )
    return GameState(turn=1, phase=Phase.VOTE, players=players)


def test_choose_master_sets_link():
    state = choose_master(night_game(), "f", "a")
    assert master_of(state, "f") == "a"


def test_butler_cannot_choose_himself():
    with pytest.raises(ValueError):
        choose_master(night_game(), "f", "f")


def test_choice_replaces_previous_master():
    state = choose_master(night_game(), "f", "a")
    state = choose_master(state, "f", "b")
    assert master_of(state, "f") == "b"


def test_poisoned_butler_sets_nothing():
    effect = Effect(type=TypeEffet.EMPOISONNE, source="poisoner", turn_start=1, phase_start=Phase.NUIT)
    butler = make_player("f", "butler", effects=(effect,))
    state = choose_master(night_game(butler), "f", "a")
    assert master_of(state, "f") is None


def test_resolve_night_sets_master():
    state = resolve_night(night_game(), {"f": ("a",)})
    assert master_of(state, "f") == "a"


def test_butler_vote_ignored_if_master_does_not_vote():
    butler = make_player("f", "butler", links={"maitre": "a"})
    state = vote_game(butler)
    # Sans le filtre, c serait exécuté avec 2 votes sur 3.
    votes = {"b": "c", "d": "e", "f": "c"}
    assert vote_result(state, votes) is None
    assert resolve_vote(state, votes).player("c").alive


def test_butler_vote_counts_if_master_votes():
    butler = make_player("f", "butler", links={"maitre": "a"})
    state = vote_game(butler)
    votes = {"a": "d", "b": "c", "f": "c"}
    assert vote_result(state, votes) == "c"


def test_butler_without_master_votes_freely():
    state = vote_game(make_player("f", "butler"))
    votes = {"b": "c", "f": "c"}
    assert vote_result(state, votes) == "c"


def test_poisoned_butler_votes_even_if_master_does_not_vote():
    effect = Effect(type=TypeEffet.EMPOISONNE, source="poisoner", turn_start=1, phase_start=Phase.NUIT)
    butler = make_player("f", "butler", effects=(effect,), links={"maitre": "a"})
    state = vote_game(butler)
    votes = {"b": "c", "f": "c"}
    assert vote_result(state, votes) == "c"