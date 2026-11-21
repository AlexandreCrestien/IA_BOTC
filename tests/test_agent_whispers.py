"""Conversation privée simulée entre deux agents : tirage du duo et résumés."""
import asyncio
import random
from collections import Counter

import pytest

import backend.agent_whispers as aw
from backend.memory_manager import MemoryManager
from backend.models import EventType, GameState, Phase, Player
from backend.rules.catalogue import ROLES

# Le joueur humain (h) est le Moine. a : Diablotin, b : Empoisonneur, c : Voyante, d : Majordome, e : Détective
ROLE_OF = {"h": "monk", "a": "imp", "b": "poisoner", "c": "psychic", "d": "butler", "e": "detective"}
AGENTS = ["a", "b", "c", "d", "e"]


def make_state(dead=()):
    return GameState(turn=2, phase=Phase.DISCUSSION, players=tuple(
        Player(id=pid, name=pid.upper(), role=ROLES[role], alive=pid not in dead) for pid, role in ROLE_OF.items()))


def make_memory(turn=2):
    memory = MemoryManager(list(ROLE_OF), names={pid: pid.upper() for pid in ROLE_OF})
    memory.set_moment(turn, Phase.DISCUSSION)
    return memory


def pair(*ids):
    return frozenset(ids)


# --- Poids ----------------------------------------------------------------------

def test_weights_follow_the_roles():
    state = make_state()
    assert aw.pair_weight(state, pair("a", "b"), [], 2) == aw.EVIL_PAIR_WEIGHT  # duo du mal
    assert aw.pair_weight(state, pair("c", "d"), [], 2) == aw.INFO_PAIR_WEIGHT  # avec la Voyante
    assert aw.pair_weight(state, pair("a", "e"), [], 2) == aw.INFO_PAIR_WEIGHT  # avec le Détective
    assert aw.pair_weight(state, pair("a", "d"), [], 2) == 1.0


def test_pair_of_the_previous_turn_is_excluded():
    state = make_state()
    assert aw.pair_weight(state, pair("a", "b"), [(1, pair("a", "b"))], 2) == 0.0
    assert aw.pair_weight(state, pair("a", "b"), [(1, pair("a", "b"))], 3) > 0


def test_repeated_pairs_and_busy_agents_are_less_likely():
    state = make_state()
    once = aw.pair_weight(state, pair("a", "b"), [(1, pair("a", "b"))], 3)
    twice = aw.pair_weight(state, pair("a", "b"), [(1, pair("a", "b")), (2, pair("a", "b"))], 4)
    assert once == aw.EVIL_PAIR_WEIGHT / 4 / (1 + 2 * aw.SOLICITATION_PENALTY)
    assert twice < once
    # a a déjà parlé avec d : le duo a-e en pâtit un peu
    assert aw.pair_weight(state, pair("a", "e"), [(1, pair("a", "d"))], 3) < aw.INFO_PAIR_WEIGHT


# --- Tirage ---------------------------------------------------------------------

def test_choice_excludes_the_human_partners_and_keeps_dead_agents():
    state = make_state(dead=["d"])
    memory = make_memory()
    rng = random.Random(0)
    seen = Counter(aw.choose_whisper_pair(state, ["b", "c", "d"], "h", memory, rng) for _ in range(300))
    assert set(seen) == {("b", "c"), ("b", "d"), ("c", "d")}  # d est mort mais reste candidat


def test_evil_pair_is_drawn_more_often_but_not_always():
    state = make_state()
    memory = make_memory()
    rng = random.Random(1)
    draws = [aw.choose_whisper_pair(state, ["a", "b", "d"], "h", memory, rng) for _ in range(2000)]
    share = draws.count(("a", "b")) / len(draws)
    assert 0.5 < share < 0.7  # 3 / (3 + 1 + 1) = 60 %


def test_meetings_with_the_human_do_not_count():
    state = make_state()
    memory = make_memory(turn=2)
    memory.set_moment(1, Phase.DISCUSSION)
    memory.add_meeting(["h", "a", "b"])  # salon du joueur au tour précédent
    memory.set_moment(2, Phase.DISCUSSION)
    rng = random.Random(0)
    assert aw.choose_whisper_pair(state, ["a", "b"], "h", memory, rng) == ("a", "b")


def test_no_pair_possible():
    state = make_state()
    memory = make_memory()
    assert aw.choose_whisper_pair(state, ["a"], "h", memory, random.Random(0)) is None
    memory.set_moment(1, Phase.DISCUSSION)
    memory.add_meeting(["a", "b"])
    memory.set_moment(2, Phase.DISCUSSION)
    assert aw.choose_whisper_pair(state, ["a", "b"], "h", memory, random.Random(0)) is None


# --- Résumés --------------------------------------------------------------------

def test_each_agent_gets_its_own_summary(monkeypatch):
    calls = []

    async def fake(profile, messages, schema, context=None):
        calls.append(messages)
        return schema(resume_1="Tu as convenu de viser C cette nuit.", resume_2="A t'a proposé de viser C.")

    monkeypatch.setattr(aw, "ask_llm_json", fake)
    state, memory = make_state(), make_memory()
    asyncio.run(aw.write_whisper_summaries(state, memory, ("a", "b")))

    assert len(calls) == 1  # un seul appel pour les deux résumés
    prompt = calls[0][-1]["content"]
    assert "Diablotin" in prompt and "Empoisonneur" in prompt
    a_events = [e for e in memory.events_for("a") if e.type == EventType.private_summary]
    b_events = [e for e in memory.events_for("b") if e.type == EventType.private_summary]
    assert [e.content for e in a_events] == ["Conversation privée avec B : Tu as convenu de viser C cette nuit."]
    assert [e.content for e in b_events] == ["Conversation privée avec A : A t'a proposé de viser C."]
    assert memory.events_for("c") == []  # personne d'autre ne connaît le contenu


def test_failed_call_leaves_a_neutral_memory(monkeypatch):
    async def failing(*args, **kwargs):
        raise ValueError("tous les modèles ont échoué")

    monkeypatch.setattr(aw, "ask_llm_json", failing)
    state, memory = make_state(), make_memory()
    asyncio.run(aw.write_whisper_summaries(state, memory, ("a", "b")))

    for pid, other in (("a", "B"), ("b", "A")):
        [event] = memory.events_for(pid)
        assert event.content == f"Conversation privée avec {other} : {aw.NEUTRAL_SUMMARY}"
        assert event.visible_to == frozenset({pid})
