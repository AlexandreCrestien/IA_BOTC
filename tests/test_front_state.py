"""Contrat entre le moteur et le front : contenu de game_state.state (game.js, players.js)."""
from backend.front_state import to_front_state, whisper_channel_id
from backend.models import GameState, Player
from backend.models.enums import Equipe, Phase
from backend.models.role import Role

IMP = Role(name_FR="Diablotin", name_EN="imp", team=Equipe.DEMON, phase=Phase.NUIT)
PSYCHIC = Role(name_FR="Voyante", name_EN="psychic", team=Equipe.VILLAGEOIS, phase=Phase.NUIT)
VILLAGER = Role(name_FR="Villageois", name_EN="villager", team=Equipe.VILLAGEOIS)


def make_state(phase: Phase = Phase.NUIT, human_alive: bool = True) -> GameState:
    return GameState(
        turn=2,
        phase=phase,
        players=(
            Player(id="h", name="Alex", role=PSYCHIC, alive=human_alive, ghost_vote=not human_alive),
            Player(id="imp", name="Imp", role=IMP),
            Player(id="mort", name="Mort", role=VILLAGER, alive=False, ghost_vote=True),
        ),
    )


def test_tour_et_nombre_de_vivants():
    view = to_front_state(make_state())
    assert view["day"] == 2
    assert view["aliveCount"] == 2


def test_phases_au_format_du_front():
    # Valeurs attendues par game.js (PHASES) et actions.js (kind)
    assert to_front_state(make_state(Phase.NUIT))["phase"] == "nuit"
    assert to_front_state(make_state(Phase.DISCUSSION))["phase"] == "discussion"
    assert to_front_state(make_state(Phase.VOTE))["phase"] == "vote"


def test_joueurs_avec_statut_et_vote_restant():
    by_id = {p["id"]: p for p in to_front_state(make_state())["players"]}
    assert by_id["h"] == {"id": "h", "name": "Alex", "alive": True, "has_vote": True}
    assert by_id["mort"]["alive"] is False
    assert by_id["mort"]["has_vote"] is True  # vote fantôme encore disponible


def test_role_des_joueurs_jamais_envoye():
    for player in to_front_state(make_state())["players"]:
        assert set(player) == {"id", "name", "alive", "has_vote"}


def test_identifiant_de_salon_prive_independant_de_l_ordre():
    assert whisper_channel_id(["imp", "h"]) == whisper_channel_id(["h", "imp"]) == "whisper_h_imp"
