import pytest

from backend.models import GameState, Phase, Player
from backend.rules import get_role
from backend.rules.vote import resolve_vote, vote_result


def make_player(id: str, role: str, **kwargs) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role), **kwargs)


def day_game(*extra: Player) -> GameState:
    players = (
        make_player("a", "imp"),
        make_player("b", "poisoner"),
        make_player("c", "monk"),
        make_player("d", "psychic"),
        make_player("e", "detective"),
        make_player("f", "butler"),
    )
    return GameState(turn=1, phase=Phase.VOTE, players=players)


def test_majority_executes():
    votes = {"a": "c", "b": "c", "d": "c", "e": None, "f": None}
    assert vote_result(day_game(), votes) == "c"
    assert not resolve_vote(day_game(), votes).player("c").alive


def test_exact_half_does_not_execute():
    votes = {"a": "c", "b": "c", "d": "e", "f": "e"}
    assert vote_result(day_game(), votes) is None
    assert resolve_vote(day_game(), votes).player("c").alive


def test_tie_does_not_execute():
    votes = {"a": "c", "b": "d"}
    assert vote_result(day_game(), votes) is None


def test_abstentions_are_not_counted():
    votes = {"a": "c", "b": None, "d": None, "e": None, "f": None}
    assert vote_result(day_game(), votes) == "c"


def test_all_abstain_no_death():
    votes = {"a": None, "b": None}
    assert vote_result(day_game(), votes) is None


def test_dead_voter_with_ghost_vote_uses_it():
    dead = make_player("e", "detective", alive=False, ghost_vote=True)
    state = day_game().replace_player(dead)
    state = resolve_vote(state, {"e": "c", "a": "c"})
    assert not state.player("e").ghost_vote
    assert not state.player("c").alive


def test_dead_voter_abstention_keeps_ghost_vote():
    dead = make_player("e", "detective", alive=False, ghost_vote=True)
    state = day_game().replace_player(dead)
    state = resolve_vote(state, {"e": None, "a": None})
    assert state.player("e").ghost_vote


def test_dead_voter_without_ghost_vote_raises():
    dead = make_player("e", "detective", alive=False, ghost_vote=False)
    state = day_game().replace_player(dead)
    with pytest.raises(ValueError):
        vote_result(state, {"e": "c"})


def test_dead_target_raises():
    dead = make_player("c", "monk", alive=False)
    state = day_game().replace_player(dead)
    with pytest.raises(ValueError):
        vote_result(state, {"a": "c"})