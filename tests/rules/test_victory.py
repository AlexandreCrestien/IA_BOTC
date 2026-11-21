from backend.models import Alignment, GameState, Phase, Player
from backend.rules import get_role, winner


def make_player(id: str, role: str, alive: bool = True) -> Player:
    p = Player(id=id, name=id.upper(), role=get_role(role))
    return p if alive else p.die()


def game(dead: tuple[str, ...] = (), phase: Phase = Phase.VOTE) -> GameState:
    """Partie à l'instant du contrôle de victoire : après le vote (par défaut) ou après la nuit."""
    players = (
        make_player("a", "reaper", alive="a" not in dead),
        make_player("b", "apothecary", alive="b" not in dead),
        make_player("c", "watchman", alive="c" not in dead),
        make_player("d", "medium", alive="d" not in dead),
        make_player("e", "inquisitor", alive="e" not in dead),
        make_player("f", "valet", alive="f" not in dead),
    )
    return GameState(turn=2, phase=phase, players=players)


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

def test_after_the_vote_evil_wins_when_only_one_good_player_is_left():
    """Faucheur + Apothicaire + un seul joueur du bien après le vote : le Faucheur le tuera la nuit suivante."""
    assert winner(game(dead=("c", "d", "e"))) == Alignment.EVIL


def test_after_the_vote_evil_wins_with_reaper_alone_against_one_good_player():
    assert winner(game(dead=("b", "c", "d", "e"))) == Alignment.EVIL


def test_after_the_night_the_last_good_player_keeps_his_vote():
    """Après la nuit, le dernier joueur du bien peut encore exécuter le Faucheur au vote (voix d'outre-tombe)."""
    assert winner(game(dead=("c", "d", "e"), phase=Phase.NIGHT)) is None


def test_after_the_night_evil_wins_when_no_good_player_is_left():
    assert winner(game(dead=("c", "d", "e", "f"), phase=Phase.NIGHT)) == Alignment.EVIL


def test_game_continues_with_two_good_players_left():
    assert winner(game(dead=("c", "d"))) is None
