import pytest
from pydantic import ValidationError

from backend.models import Effect, GameState, Phase, Player, EffectType
from backend.rules import get_role


def player(id: str, alive: bool = True) -> Player:
    p = Player(id=id, name=id.capitalize(), role=get_role("monk"))
    return p if alive else p.die()


def night_2_protection() -> Effect:
    return Effect(
        type=EffectType.PROTECTED,
        source="monk",
        turn_start=2,
        phase_start=Phase.NIGHT,
        turn_end=2,
        phase_end=Phase.DISCUSSION,
    )


def state() -> GameState:
    return GameState(
        players=(player("odette"), player("brutus"), player("gaspard", alive=False)),
    )


def test_initial_state_is_night_turn_1():
    s = GameState()
    assert s.turn == 1 and s.phase == Phase.NIGHT and s.players == ()


def test_night_moves_to_discussion_same_turn():
    s = GameState().next_phase()
    assert s.turn == 1 and s.phase == Phase.DISCUSSION


def test_discussion_moves_to_vote_same_turn():
    s = GameState(phase=Phase.DISCUSSION).next_phase()
    assert s.turn == 1 and s.phase == Phase.VOTE


def test_vote_moves_to_next_turn_night():
    s = GameState(phase=Phase.VOTE).next_phase()
    assert s.turn == 2 and s.phase == Phase.NIGHT


def test_phase_change_removes_expired_effects():
    s = GameState(turn=2, phase=Phase.NIGHT, players=(player("odette").add_effect(night_2_protection()),))
    s = s.next_phase()
    assert not s.player("odette").has_effect(EffectType.PROTECTED)


def test_unknown_player_raises_keyerror():
    with pytest.raises(KeyError):
        state().player("inconnu")


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


def test_turn_zero_refused():
    with pytest.raises(ValidationError):
        GameState(turn=0)


def test_state_is_immutable():
    with pytest.raises(ValidationError):
        state().turn = 5


def test_str_summarizes_game():
    text = str(state().next_phase())
    assert text.startswith("Tour 1, discussion")
    assert "Vivants (2) : Odette (monk), Brutus (monk)" in text
    assert "Morts : Gaspard" in text


def test_str_shows_effects():
    s = GameState(players=(player("odette").add_effect(night_2_protection()),))
    assert "[protege]" in str(s)

def test_power_is_reset_at_night():
    used = player("odette").model_copy(update={"power_used": True})
    s = GameState(turn=1, phase=Phase.VOTE, players=(used,)).next_phase()
    assert s.phase == Phase.NIGHT and not s.player("odette").power_used


def test_power_stays_used_during_the_day():
    used = player("odette").model_copy(update={"power_used": True})
    s = GameState(turn=1, phase=Phase.NIGHT, players=(used,)).next_phase()
    assert s.player("odette").power_used
