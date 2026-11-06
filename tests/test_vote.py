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

# --- Vote sur une désignation (pour / contre) -------------------------------------

from backend.rules.vote import check_nomination, nomination_result, resolve_nomination  # noqa: E402

ALL_FOR = {"a": True, "b": True, "c": True, "d": True, "e": False, "f": False}


def test_majority_of_voters_for_executes():
    assert nomination_result(day_game(), "c", ALL_FOR) == "c"
    assert not resolve_nomination(day_game(), "c", ALL_FOR).player("c").alive


def test_half_of_voters_is_not_enough():
    ballots = {"a": True, "b": True, "c": True, "d": False, "e": False, "f": False}
    assert nomination_result(day_game(), "c", ballots) is None


def test_majority_is_counted_on_living_players():
    """2 pour sur 6 vivants : pas d'exécution, même si les autres n'ont pas voté."""
    assert nomination_result(day_game(), "c", {"a": True, "b": True, "d": False}) is None


def test_dead_against_does_not_weigh_on_the_vote():
    """4 vivants + 2 morts : 3 « pour » vivants suffisent, les « contre » des morts ne comptent pas."""
    state = day_game()
    for pid in ("e", "f"):
        state = state.replace_player(state.player(pid).die())
    ballots = {"a": True, "b": True, "c": False, "d": True, "e": False, "f": False}
    assert nomination_result(state, "c", ballots) == "c"


def test_dead_for_counts_and_uses_the_ghost_vote():
    """4 vivants : 2 « pour » vivants + 1 « pour » d'un mort = 3 > 2, exécution."""
    state = day_game()
    for pid in ("e", "f"):
        state = state.replace_player(state.player(pid).die())
    ballots = {"a": True, "b": True, "c": False, "d": False, "e": True, "f": False}
    after = resolve_nomination(state, "c", ballots)
    assert not after.player("c").alive
    assert not after.player("e").can_vote and after.player("f").can_vote


def test_no_ballot_no_execution():
    assert nomination_result(day_game(), "c", {}) is None


def test_dead_voter_for_uses_ghost_vote():
    state = day_game()
    state = state.replace_player(state.player("e").die())
    after = resolve_nomination(state, "c", {"a": True, "e": True})
    assert not after.player("e").can_vote


def test_dead_voter_against_keeps_ghost_vote():
    state = day_game()
    state = state.replace_player(state.player("e").die())
    after = resolve_nomination(state, "c", {"a": True, "e": False})
    assert after.player("e").can_vote


def test_butler_for_does_not_count_if_master_votes_against():
    state = day_game().replace_player(make_player("f", "butler", links={"maitre": "a"}))
    ballots = {"a": False, "b": True, "c": True, "f": True}
    # sans le Majordome : 2 pour sur 4 votants -> égalité
    assert nomination_result(state, "c", ballots) is None


def test_dead_cannot_nominate_or_be_nominated():
    state = day_game()
    state = state.replace_player(state.player("e").die())
    with pytest.raises(ValueError):
        check_nomination(state, "e", "c")
    with pytest.raises(ValueError):
        check_nomination(state, "a", "e")
    check_nomination(state, "a", "c")
