"""Morts de la nuit, votes et exécutions : annoncés publiquement dans la mémoire de tous les joueurs."""
from backend.engine.steps import Ballot, record_night_deaths, record_vote, vote_ballots
from backend.ai.memory_manager import MemoryManager
from backend.models import EventType, GameState, Phase, Player
from backend.rules import get_role

NAMES = {"a": "Ada", "b": "Bob", "c": "Cléo", "d": "Dan"}
ROLES = {"a": "reaper", "b": "apothecary", "c": "watchman", "d": "medium"}


def make_state(dead=()):
    players = tuple(Player(id=pid, name=NAMES[pid], role=get_role(ROLES[pid]), alive=pid not in dead)
                    for pid in NAMES)
    return GameState(turn=2, phase=Phase.VOTE, players=players)


def make_memory(phase=Phase.VOTE):
    memory = MemoryManager(list(NAMES), names=NAMES)
    memory.set_moment(2, phase)
    return memory


def public_lines(memory, reader="c"):
    return [(e.type, e.content) for e in memory.events_for(reader) if e.visible_to is None]


def test_night_deaths_are_public():
    memory = make_memory(Phase.NIGHT)
    record_night_deaths(make_state(dead=["d"]), ("d",), memory)
    assert public_lines(memory) == [(EventType.DEATH, "Dan est mort·e cette nuit.")]
    assert memory.events_for("a")[0].phase == Phase.NIGHT


def test_night_without_death_is_announced_too():
    memory = make_memory(Phase.NIGHT)
    record_night_deaths(make_state(), (), memory)
    assert public_lines(memory) == [(EventType.DEATH, "Personne n'est mort cette nuit.")]


def test_votes_and_execution_are_public_with_ghost_votes():
    memory = make_memory()
    votes = {"a": "c", "b": "c", "c": None, "d": "a"}  # Dan est déjà mort : voix d'outre-tombe
    record_vote(make_state(dead=["d"]), votes, "c", memory)
    assert public_lines(memory, reader="b") == [
        (EventType.VOTE, "Votes : Ada → Cléo, Bob → Cléo, Cléo → personne, Dan → Ada (voix d'outre-tombe)."),
        (EventType.DEATH, "Cléo est exécuté·e par le village."),
    ]


def test_no_execution_is_announced():
    memory = make_memory()
    record_vote(make_state(), {"a": "b", "b": "a"}, None, memory)
    assert public_lines(memory)[-1] == (EventType.DEATH, "Personne n'est exécuté aujourd'hui.")


def test_ghost_abstention_is_not_marked():
    memory = make_memory()
    record_vote(make_state(dead=["d"]), {"d": None}, None, memory)
    assert public_lines(memory)[0] == (EventType.VOTE, "Votes : Dan → personne.")


# --- Bulletins : seuls les votes qui comptent utilisent la voix d'outre-tombe ------------


def make_state_with_valet(dead=()):
    """Partie avec un Valet (v) dont le maître est Ada (a)."""
    players = tuple(Player(id=pid, name=NAMES[pid], role=get_role(ROLES[pid]), alive=pid not in dead)
                    for pid in NAMES)
    valet = Player(id="v", name="Val", role=get_role("valet"), alive="v" not in dead, links={"master": "a"})
    return GameState(turn=2, phase=Phase.VOTE, players=players + (valet,))


def test_ballots_follow_the_valet_rule_without_revealing_anything():
    """Par sécurité : si un vote de Valet bloqué arrivait quand même, il apparaîtrait comme une simple
    abstention (aucune mention qui révélerait son rôle) et n'utiliserait pas de voix d'outre-tombe."""
    state = make_state_with_valet(dead=["v"])
    [ballot] = [b for b in vote_ballots(state, {"a": None, "v": "c"}) if b.voter == "v"]
    assert ballot == Ballot("v", None, ghost=False)
    memory = make_memory()
    record_vote(state, {"a": None, "b": "c", "v": "c"}, None, memory)
    assert public_lines(memory)[0] == (EventType.VOTE, "Votes : Ada → personne, Bob → Cléo, Val → personne.")


def test_dead_player_abstaining_does_not_use_his_ghost_vote():
    """Bug corrigé : un mort qui s'abstenait était marqué « outre-tombe » à l'écran."""
    ballots = vote_ballots(make_state(dead=["d"]), {"d": None, "a": "b"})
    assert ballots[0] == Ballot("d", None, ghost=False)
