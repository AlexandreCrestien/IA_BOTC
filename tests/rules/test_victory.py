from backend.models import Alignment, GameState, Phase, Player
from backend.rules import get_role, winner


def make_player(id: str, role: str, alive: bool = True) -> Player:
    p = Player(id=id, name=id.upper(), role=get_role(role))
    return p if alive else p.die()


def game(dead: tuple[str, ...] = ()) -> GameState:
    players = (
        make_player("a", "reaper", alive="a" not in dead),
        make_player("b", "apothecary", alive="b" not in dead),
        make_player("c", "watchman", alive="c" not in dead),
        make_player("d", "medium", alive="d" not in dead),
        make_player("e", "inquisitor", alive="e" not in dead),
        make_player("f", "valet", alive="f" not in dead),
    )
    return GameState(turn=2, phase=Phase.VOTE, players=players)


def test_game_continues_at_start():
    assert winner(game()) is None


def test_good_wins_when_demon_dies():
    assert winner(game(dead=("a",))) == Alignment.GOOD


def test_evil_wins_when_no_good_player_alive():
    assert winner(game(dead=("c", "d", "e", "f"))) == Alignment.EVIL


def test_accomplice_alive_does_not_keep_evil_in_game():
    # Le complice vivant ne compte pas : seul le bien vivant maintient la partie.
    assert winner(game(dead=("c", "d", "e", "f"))) == Alignment.EVIL


def test_good_wins_when_demon_and_good_both_dead():
    assert winner(game(dead=("a", "c", "d", "e", "f"))) == Alignment.GOOD