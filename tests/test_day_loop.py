from backend.game_engine import collect_votes, play_day
from backend.models import GameState, Phase, Player
from backend.rules import get_role


def make_player(id: str, role: str, **kwargs) -> Player:
    return Player(id=id, name=id.upper(), role=get_role(role), **kwargs)


def day_game(*overrides: Player) -> GameState:
    players = [
        make_player("a", "imp"),
        make_player("b", "poisoner"),
        make_player("c", "monk"),
        make_player("d", "psychic"),
        make_player("e", "detective"),
        make_player("f", "butler"),
    ]
    by_id = {p.id: p for p in overrides}
    players = tuple(by_id.get(p.id, p) for p in players)
    return GameState(turn=2, phase=Phase.VOTE, players=players, channels=(), log=())


def vote_for_c(state: GameState, player_id: str):
    return "c"


def test_everyone_who_can_vote_is_collected():
    votes = collect_votes(day_game())
    assert set(votes) == {"a", "b", "c", "d", "e", "f"}


def test_dead_voter_without_ghost_vote_is_excluded():
    state = day_game(make_player("e", "detective", alive=False, ghost_vote=False))
    assert "e" not in collect_votes(state)


def test_missing_or_invalid_choice_is_abstention():
    votes = collect_votes(day_game(), choose=lambda s, pid: None)
    assert all(target is None for target in votes.values())


def test_dead_target_becomes_abstention():
    state = day_game(make_player("c", "monk", alive=False))
    votes = collect_votes(state, choose=lambda s, pid: "c")
    assert all(target is None for target in votes.values())


def test_unanimous_vote_executes_the_target():
    new_state, votes, executed = play_day(day_game(), choose=vote_for_c)
    assert executed == "c"
    assert not new_state.player("c").alive


def test_no_vote_no_execution():
    new_state, _, executed = play_day(day_game(), choose=lambda s, pid: None)
    assert executed is None
    assert all(p.alive for p in new_state.players)