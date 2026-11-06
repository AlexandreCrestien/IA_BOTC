import random

from backend.game_engine import _info_text, announce_night, announce_vote, setup_game
from backend.memory_manager import MemoryManager
from backend.models import EventType, GameState, Phase, Player
from backend.rules import first_night_info, get_role

NAMES = {"a": "Ada", "b": "Bob", "c": "Cléo", "d": "Dan", "e": "Eva", "f": "Fay"}
ROLES = {"a": "imp", "b": "poisoner", "c": "monk", "d": "psychic", "e": "detective", "f": "butler"}


def game() -> GameState:
    players = tuple(Player(id=pid, name=NAMES[pid], role=get_role(ROLES[pid])) for pid in NAMES)
    return GameState(turn=1, phase=Phase.NUIT, players=players, channels=())


def memory() -> MemoryManager:
    return MemoryManager(list(NAMES), names=NAMES)


def infos_by_viewer(state):
    return {info.viewer_id: _info_text(state, info) for info in first_night_info(state, random.Random(1))}


def test_demon_learns_his_minion():
    text = infos_by_viewer(game())["a"]
    assert "tu es Diablotin, le démon" in text and "Ton sbire est : Bob" in text


def test_minion_learns_the_demon():
    text = infos_by_viewer(game())["b"]
    assert "tu es Empoisonneur" in text and "Le démon est : Ada" in text


def test_detective_sees_a_minion_not_the_demon():
    text = infos_by_viewer(game())["e"]
    assert "l'un d'eux est un sbire" in text and "Diablotin" not in text
    assert "Bob" in text


def test_setup_gives_each_evil_player_his_own_role():
    state, _, mem = setup_game(NAMES, "f", ["agitator", "clown", "observer", "paranoid", "strategist"],
                               random.Random(3))
    for player in state.players:
        if player.role.team.value in ("demon", "sbire"):
            [event] = mem.events_for(player.id)
            assert f"tu es {player.role.name_FR}" in event.content


def test_morning_announcement_names_the_dead():
    mem, state = memory(), game()
    announce_night(mem, state, ("c",))
    [event] = mem.events_for("a")
    assert event.type == EventType.death
    assert event.content == "Le jour 1 se lève. Mort cette nuit : Cléo."


def test_morning_announcement_without_death():
    mem = memory()
    announce_night(mem, game(), ())
    assert mem.events_for("b")[0].content == "Le jour 1 se lève. Personne n'est mort cette nuit."


def test_vote_announcement_lists_votes_and_execution():
    mem = memory()
    announce_vote(mem, game(), {"a": "c", "b": None}, "c")
    contents = [e.content for e in mem.events_for("d")]
    assert contents == ["Votes : Ada → Cléo, Bob → personne.", "Cléo est exécuté."]


def test_vote_announcement_without_execution():
    mem = memory()
    announce_vote(mem, game(), {}, None)
    assert [e.content for e in mem.events_for("d")] == ["Votes : aucun vote.", "Personne n'est exécuté."]


def test_memory_listener_receives_every_event():
    mem, seen = memory(), []
    mem.subscribe(seen.append)
    mem.add_public(EventType.announcement, "a", "Bonjour")
    mem.add_personal(EventType.role_info, "a", "Secret", "a")
    assert [e.content for e in seen] == ["Bonjour", "Secret"]
