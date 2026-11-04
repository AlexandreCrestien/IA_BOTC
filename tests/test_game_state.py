import pytest
from pydantic import ValidationError

from backend.models import Channel, Effect, GameEvent, GameState, Phase, Player, TypeEffet
from backend.rules import get_role


def player(id: str, alive: bool = True) -> Player:
    p = Player(id=id, name=id.capitalize(), role=get_role("Moine"))
    return p if alive else p.die()


def night_2_protection() -> Effect:
    return Effect(
        type=TypeEffet.PROTEGE,
        source="Moine",
        turn_start=2,
        phase_start=Phase.NUIT,
        turn_end=2,
        phase_end=Phase.DISCUSSION,
    )


def state() -> GameState:
    return GameState(
        players=(player("odette"), player("brutus"), player("gaspard", alive=False)),
        channels=(Channel(id="village", name="Place du village", public=True, members=("odette", "brutus")),),
    )


def test_initial_state_is_night_turn_1():
    s = GameState()
    assert s.turn == 1 and s.phase == Phase.NUIT and s.players == () and s.log == ()


def test_night_moves_to_discussion_same_turn():
    s = GameState().next_phase()
    assert s.turn == 1 and s.phase == Phase.DISCUSSION


def test_discussion_moves_to_vote_same_turn():
    s = GameState(phase=Phase.DISCUSSION).next_phase()
    assert s.turn == 1 and s.phase == Phase.VOTE


def test_vote_moves_to_next_turn_night():
    s = GameState(phase=Phase.VOTE).next_phase()
    assert s.turn == 2 and s.phase == Phase.NUIT


def test_phase_change_removes_expired_effects():
    s = GameState(turn=2, phase=Phase.NUIT, players=(player("odette").add_effect(night_2_protection()),))
    s = s.next_phase()
    assert not s.player("odette").has_effect(TypeEffet.PROTEGE)


def test_unknown_player_raises_keyerror():
    with pytest.raises(KeyError):
        state().player("inconnu")


def test_unknown_channel_raises_keyerror():
    with pytest.raises(KeyError):
        state().channel("inconnu")


def test_duplicate_player_ids_refused():
    with pytest.raises(ValidationError):
        GameState(players=(player("odette"), player("odette")))


def test_replace_player_changes_only_that_player():
    s = state()
    dead = s.player("odette").die()
    new_state = s.replace_player(dead)
    assert not new_state.player("odette").alive
    assert new_state.player("brutus") == s.player("brutus")
    assert s.player("odette").alive


def test_alive_players_excludes_dead():
    ids = [p.id for p in state().alive_players()]
    assert ids == ["odette", "brutus"]


def test_add_event():
    s = state().add_event(GameEvent(type="mort", turn=1, phase=Phase.NUIT))
    assert len(s.log) == 1


def test_public_log_visible_to_everyone():
    s = state().add_event(GameEvent(type="vote", turn=1, phase=Phase.DISCUSSION))
    assert len(s.log_visible_to("gaspard")) == 1


def test_private_log_visible_only_to_recipients():
    event = GameEvent(type="sonde", turn=1, phase=Phase.NUIT, public=False, recipients=("odette",))
    s = state().add_event(event)
    assert len(s.log_visible_to("odette")) == 1
    assert s.log_visible_to("brutus") == ()


def test_engine_only_log_invisible_to_players():
    event = GameEvent(type="interne", turn=1, phase=Phase.NUIT, public=False)
    s = state().add_event(event)
    assert s.log_visible_to("odette") == ()


def test_replace_channel():
    s = state()
    closed = s.channel("village").close()
    assert not s.replace_channel(closed).channel("village").open


def test_turn_zero_refused():
    with pytest.raises(ValidationError):
        GameState(turn=0)


def test_state_is_immutable():
    with pytest.raises(ValidationError):
        state().turn = 5


def test_str_summarizes_game():
    text = str(state().next_phase())
    assert text.startswith("Tour 1, discussion")
    assert "Vivants (2) : Odette (Moine), Brutus (Moine)" in text
    assert "Morts : Gaspard" in text


def test_str_shows_effects():
    s = GameState(players=(player("odette").add_effect(night_2_protection()),))
    assert "[protege]" in str(s)