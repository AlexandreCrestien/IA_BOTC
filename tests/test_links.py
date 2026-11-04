import pytest

from backend.models import Player
from backend.rules import get_role, set_link


def player(id: str, role: str) -> Player:
    return Player(id=id, name=id.capitalize(), role=get_role(role))


def test_butler_sets_a_master():
    p = set_link(player("m1", "butler"), "maitre", "odette")
    assert p.link("maitre") == "odette"


def test_seer_sets_a_false_lead():
    p = set_link(player("v1", "psychic"), "fausse_piste", "odette")
    assert p.link("fausse_piste") == "odette"


def test_link_key_not_allowed_refused():
    with pytest.raises(ValueError):
        set_link(player("m1", "butler"), "fausse_piste", "odette")


def test_role_without_links_refuses_everything():
    with pytest.raises(ValueError):
        set_link(player("m1", "monk"), "maitre", "odette")


def test_player_cannot_target_self():
    with pytest.raises(ValueError):
        set_link(player("m1", "butler"), "maitre", "m1")


def test_set_link_returns_new_object():
    original = player("m1", "butler")
    new = set_link(original, "maitre", "odette")
    assert original.link("maitre") is None and new.link("maitre") == "odette"