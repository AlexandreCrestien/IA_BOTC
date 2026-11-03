import pytest
from pydantic import ValidationError

from backend.models import Effet, Phase, TypeEffet


def protection_nuit_2() -> Effet:
    """Protection posée la nuit 2, qui dure jusqu'au début du jour 2."""
    return Effet(
        type=TypeEffet.PROTEGE,
        source="Moine",
        tour_debut=2,
        phase_debut=Phase.NUIT,
        tour_fin=2,
        phase_fin=Phase.DISCUSSION,
    )


def test_protection_active_pendant_la_nuit():
    assert not protection_nuit_2().est_expire(2, Phase.NUIT)


def test_protection_retiree_au_debut_du_jour():
    assert protection_nuit_2().est_expire(2, Phase.DISCUSSION)


@pytest.mark.parametrize("tour, phase", [(3, Phase.NUIT), (3, Phase.DISCUSSION), (10, Phase.NUIT)])
def test_protection_toujours_expiree_apres_sa_fin(tour, phase):
    assert protection_nuit_2().est_expire(tour, phase)


def test_effet_permanent_jamais_expire():
    poison = Effet(type=TypeEffet.EMPOISONNE, source="Test", tour_debut=1, phase_debut=Phase.NUIT)
    assert not poison.est_expire(10, Phase.DISCUSSION)


def test_fin_sans_phase_refusee():
    with pytest.raises(ValidationError):
        Effet(type=TypeEffet.PROTEGE, source="Moine", tour_debut=2, phase_debut=Phase.NUIT, tour_fin=2)


def test_fin_avant_debut_refusee():
    with pytest.raises(ValidationError):
        Effet(
            type=TypeEffet.PROTEGE,
            source="Moine",
            tour_debut=3,
            phase_debut=Phase.DISCUSSION,
            tour_fin=3,
            phase_fin=Phase.NUIT,
        )


def test_effet_immutable():
    effet = protection_nuit_2()
    with pytest.raises(ValidationError):
        effet.source = "autre"