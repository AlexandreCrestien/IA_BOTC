import pytest
from pydantic import ValidationError

from backend.models import Effect, Phase, EffectType


def night_2_protection() -> Effect:
    """Protection posée la nuit 2, qui dure jusqu'au début du jour 2."""
    return Effect(
        type=EffectType.PROTECTED,
        source="monk",
        turn_start=2,
        phase_start=Phase.NIGHT,
        turn_end=2,
        phase_end=Phase.DISCUSSION,
    )


def test_protection_active_during_night():
    assert not night_2_protection().is_expired(2, Phase.NIGHT)


def test_protection_removed_at_start_of_day():
    assert night_2_protection().is_expired(2, Phase.DISCUSSION)


@pytest.mark.parametrize("turn, phase", [(3, Phase.NIGHT), (3, Phase.DISCUSSION), (10, Phase.NIGHT)])
def test_protection_still_expired_after_its_end(turn, phase):
    assert night_2_protection().is_expired(turn, phase)


def test_permanent_effect_never_expires():
    poison = Effect(type=EffectType.POISONED, source="Test", turn_start=1, phase_start=Phase.NIGHT)
    assert not poison.is_expired(10, Phase.DISCUSSION)


def test_end_without_phase_refused():
    with pytest.raises(ValidationError):
        Effect(type=EffectType.PROTECTED, source="monk", turn_start=2, phase_start=Phase.NIGHT, turn_end=2)


def test_end_before_start_refused():
    with pytest.raises(ValidationError):
        Effect(
            type=EffectType.PROTECTED,
            source="monk",
            turn_start=3,
            phase_start=Phase.DISCUSSION,
            turn_end=3,
            phase_end=Phase.NIGHT,
        )


def test_effect_is_immutable():
    effect = night_2_protection()
    with pytest.raises(ValidationError):
        effect.source = "autre"