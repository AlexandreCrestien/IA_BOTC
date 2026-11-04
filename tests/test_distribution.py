import random

import pytest

from backend.models import Alignement
from backend.rules import SIX_PLAYER_ROLES, choose_false_lead, distribute_roles

IDS = ["j1", "j2", "j3", "j4", "j5", "j6"]


def test_each_role_exactly_once():
    roles = distribute_roles(IDS, random.Random(1))
    assert sorted(r.name for r in roles.values()) == sorted(SIX_PLAYER_ROLES)


def test_each_player_gets_a_role():
    roles = distribute_roles(IDS, random.Random(1))
    assert set(roles) == set(IDS)


def test_only_one_diablotin():
    roles = distribute_roles(IDS, random.Random(2))
    assert sum(1 for r in roles.values() if r.name == "imp") == 1


def test_same_seed_same_distribution():
    assert distribute_roles(IDS, random.Random(3)) == distribute_roles(IDS, random.Random(3))


def test_distribution_varies_with_seed():
    results = {
        tuple(sorted((k, v.name) for k, v in distribute_roles(IDS, random.Random(g)).items()))
        for g in range(20)
    }
    assert len(results) > 1


def test_wrong_number_of_players_refused():
    with pytest.raises(ValueError):
        distribute_roles(IDS[:5], random.Random(1))


def test_duplicate_ids_refused():
    with pytest.raises(ValueError):
        distribute_roles(["j1", "j1", "j2", "j3", "j4", "j5"], random.Random(1))


@pytest.mark.parametrize("seed", range(30))
def test_false_lead_is_never_demon_or_seer(seed):
    roles = distribute_roles(IDS, random.Random(seed))
    lead = choose_false_lead(roles, random.Random(seed))
    assert lead in roles
    assert roles[lead].name not in ("imp", "psychic")


@pytest.mark.parametrize("seed", range(30))
def test_false_lead_is_a_good_player(seed):
    roles = distribute_roles(IDS, random.Random(seed))
    lead = choose_false_lead(roles, random.Random(seed))
    assert roles[lead].alignment == Alignement.BON