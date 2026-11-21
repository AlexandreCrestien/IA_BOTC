"""Morts de la nuit, votes et exécutions : annoncés publiquement dans la mémoire de tous les joueurs."""
from backend.engine.steps import record_night_deaths, record_vote
from backend.ai.memory_manager import MemoryManager
from backend.models import EventType, GameState, Phase, Player
from backend.rules import get_role

NAMES = {"a": "Ada", "b": "Bob", "c": "Cléo", "d": "Dan"}
ROLES = {"a": "imp", "b": "poisoner", "c": "monk", "d": "psychic"}


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
    votes = {"a": "c", "b": "c", "c": None, "d": "a"}  # Dan est déjà mort : vote fantôme
    record_vote(make_state(dead=["d"]), votes, "c", memory)
    assert public_lines(memory, reader="b") == [
        (EventType.VOTE, "Votes : Ada → Cléo, Bob → Cléo, Cléo → personne, Dan → Ada (vote fantôme)."),
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
