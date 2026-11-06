import pytest

from backend.memory_manager import EventType, MemoryManager, Phase, game_master


@pytest.fixture
def memory():
    return MemoryManager(["ana", "bruno", "carla"])


def contents(events):
    return [e.content for e in events]


def test_public_event_is_seen_by_everyone(memory):
    memory.add_public(EventType.announcement, game_master, "Le jour commence")
    for player in ["ana", "bruno", "carla"]:
        assert contents(memory.events_for(player)) == ["Le jour commence"]


def test_private_event_is_seen_only_by_participants(memory):
    memory.add_private(EventType.private_summary, "ana", "On soupçonne carla", {"bruno"})
    assert contents(memory.events_for("ana")) == ["On soupçonne carla"]
    assert contents(memory.events_for("bruno")) == ["On soupçonne carla"]
    assert memory.events_for("carla") == []


def test_personal_event_is_seen_only_by_its_player(memory):
    memory.add_personal(EventType.night_info, game_master, "Ta vision : Oui", "ana")
    assert contents(memory.events_for("ana")) == ["Ta vision : Oui"]
    assert memory.events_for("bruno") == []
    assert memory.events_for("carla") == []


def test_author_is_added_to_readers(memory):
    event = memory.add_private(EventType.private_summary, "ana", "Salut", {"bruno"})
    assert event.visible_to == {"ana", "bruno"}


def test_game_master_is_never_added_to_readers(memory):
    event = memory.add_personal(EventType.role_info, game_master, "Tu es le monk", "ana")
    assert event.visible_to == {"ana"}


def test_unknown_reader_raises(memory):
    with pytest.raises(ValueError, match="bruna"):
        memory.add_personal(EventType.night_info, game_master, "x", "bruna")


def test_empty_readers_raise(memory):
    with pytest.raises(ValueError):
        memory.add_private(EventType.private_summary, "ana", "x", set())


def test_unknown_author_raises(memory):
    with pytest.raises(ValueError, match="bruna"):
        memory.add_public(EventType.public_message, "bruna", "x")


def test_unknown_player_cannot_read(memory):
    with pytest.raises(ValueError):
        memory.events_for(game_master)


def test_duplicate_player_ids_raise():
    with pytest.raises(ValueError, match="ana"):
        MemoryManager(["ana", "bruno", "ana"])


def test_game_master_id_is_reserved():
    with pytest.raises(ValueError):
        MemoryManager(["ana", game_master])


def test_events_keep_chronological_order_and_phase(memory):
    memory.set_moment(1, Phase.NUIT)
    memory.add_public(EventType.announcement, game_master, "Nuit 1")
    memory.set_moment(1, Phase.DISCUSSION)
    memory.add_public(EventType.announcement, game_master, "Discussion 1")
    memory.set_moment(1, Phase.VOTE)
    memory.add_public(EventType.announcement, game_master, "Vote 1")
    memory.set_moment(2, Phase.NUIT)
    memory.add_public(EventType.announcement, game_master, "Nuit 2")

    events = memory.events_for("ana")
    assert [(e.turn, e.phase) for e in events] == [
        (1, Phase.NUIT),
        (1, Phase.DISCUSSION),
        (1, Phase.VOTE),
        (2, Phase.NUIT),
    ]

def test_returned_list_does_not_change_memory(memory):
    memory.add_public(EventType.announcement, game_master, "Le jour commence")
    memory.events_for("ana").clear()
    assert len(memory.events_for("ana")) == 1


def test_two_games_do_not_share_events():
    game_1 = MemoryManager(["ana", "bruno"])
    game_2 = MemoryManager(["ana", "bruno"])
    game_1.add_public(EventType.announcement, game_master, "Partie 1")
    assert game_2.events_for("ana") == []


def test_context_shows_channel_and_author(memory):
    memory.add_personal(EventType.role_info, game_master, "Tu es le monk.", "ana")
    memory.add_private(EventType.private_summary, "ana", "On soupçonne carla.", {"bruno"})
    memory.add_public(EventType.public_message, "carla", "Bonjour !")

    assert memory.context_for("ana").splitlines() == [
        "[Nuit 1] (personnel) Maître du Jeu : Tu es le monk.",
        "[Nuit 1] (privé avec bruno) Toi : On soupçonne carla.",
        "[Nuit 1] (public) carla : Bonjour !",
    ]


def test_context_never_leaks_private_content(memory):
    memory.add_private(EventType.private_summary, "ana", "SECRET", {"bruno"})
    assert "SECRET" not in memory.context_for("carla")


def test_context_when_empty(memory):
    assert memory.context_for("ana") == "Aucun événement pour l'instant."


def test_private_partners(memory):
    memory.add_private(EventType.private_summary, "ana", "Salut", {"bruno"})
    memory.add_public(EventType.public_message, "carla", "Bonjour à tous")
    assert memory.private_partners("ana") == {"bruno"}
    assert memory.private_partners("bruno") == {"ana"}
    assert memory.private_partners("carla") == set()  # un message public n'est pas une conversation privée



# --- Noms affichés (complète tests/test_memory_names.py) ---------------------------

def test_names_replace_ids_in_context():
    """Les agents connaissent les joueurs par leur nom : l'historique ne doit pas montrer les ids."""
    memory = MemoryManager(["p1", "p2", "p3"], names={"p1": "Ana", "p2": "Bruno", "p3": "Carla"})
    memory.add_private(EventType.private_summary, "p2", "On soupçonne Carla.", {"p1", "p2"})
    memory.add_public(EventType.public_message, "p3", "Bonjour !")
    memory.add_public(EventType.announcement, game_master, "Le jour se lève.")

    assert memory.context_for("p1").splitlines() == [
        "[Nuit 1] (privé avec Bruno) Bruno : On soupçonne Carla.",
        "[Nuit 1] (public) Carla : Bonjour !",
        "[Nuit 1] (public) Maître du Jeu : Le jour se lève.",
    ]


def test_name_of_falls_back_to_id():
    assert MemoryManager(["ana"]).name_of("ana") == "ana"
