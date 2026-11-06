import pytest

from backend.memory_manager import MemoryManager
from backend.models import EventType, Phase


def test_context_shows_names_not_ids():
    memory = MemoryManager(["a", "b"], names={"a": "Ada", "b": "Bob"})
    memory.set_moment(1, Phase.DISCUSSION)
    memory.add_public(EventType.public_message, "a", "Salut")
    assert "Ada : Salut" in memory.context_for("b")
    assert "(public) a : Salut" not in memory.context_for("b")


def test_private_channel_shows_names():
    memory = MemoryManager(["a", "b"], names={"a": "Ada", "b": "Bob"})
    memory.add_private(EventType.private_summary, "a", "secret", {"b"})
    assert "privé avec Ada" in memory.context_for("b")


def test_names_must_match_player_ids():
    with pytest.raises(ValueError):
        MemoryManager(["a", "b"], names={"a": "Ada"})