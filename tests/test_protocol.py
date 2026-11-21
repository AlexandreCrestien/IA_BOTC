"""Contrat entre le moteur et le front : contenu de game_state.state (game.js, players.js)."""
from backend.server.protocol import to_front_state, whisper_channel_id
from backend.models import GameState, Player
from backend.models.enums import Phase
from backend.rules import get_role

IMP = get_role("imp")
PSYCHIC = get_role("psychic")
VILLAGER = get_role("detective")  # villageois sans action de nuit


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
    view = to_front_state(make_state()).model_dump()
    assert view["day"] == 2
    assert view["aliveCount"] == 2


def test_phases_au_format_du_front():
    # Valeurs attendues par game.js (PHASES) et actions.js (kind)
    assert to_front_state(make_state(Phase.NUIT)).model_dump()["phase"] == "nuit"
    assert to_front_state(make_state(Phase.DISCUSSION)).model_dump()["phase"] == "discussion"
    assert to_front_state(make_state(Phase.VOTE)).model_dump()["phase"] == "vote"


def test_joueurs_avec_statut_et_vote_restant():
    by_id = {p["id"]: p for p in to_front_state(make_state()).model_dump()["players"]}
    assert by_id["h"] == {"id": "h", "name": "Alex", "alive": True, "has_vote": True}
    assert by_id["mort"]["alive"] is False
    assert by_id["mort"]["has_vote"] is True  # vote fantôme encore disponible


def test_role_des_joueurs_jamais_envoye():
    for player in to_front_state(make_state()).model_dump()["players"]:
        assert set(player) == {"id", "name", "alive", "has_vote"}


def test_identifiant_de_salon_prive_independant_de_l_ordre():
    assert whisper_channel_id(["imp", "h"]) == whisper_channel_id(["h", "imp"]) == "whisper_h_imp"


# --- Relais des demandes du moteur vers le front -------------------------------------

import asyncio  # noqa: E402

from backend.server import protocol  # noqa: E402
from backend.server.session import GameSession  # noqa: E402


def test_relais_retient_la_demande_et_envoie_des_identifiants(monkeypatch):
    sent = []

    async def fake_send(player_id, message):
        sent.append(message)

    monkeypatch.setattr(protocol.manager, "send_to_player", fake_send)
    session = GameSession(human_id="h")
    state = make_state(Phase.VOTE)

    async def scenario():
        task = asyncio.create_task(protocol.forward_requests(session))
        await session.port.requests.put({"kind": "vote", "state": state, "targets": ["imp", "h"]})
        await asyncio.sleep(0.01)
        assert session.waits_for("vote")
        assert session.state is state  # l'état joint à la demande devient l'état courant

        # Une simple information (message public d'une IA) n'attend pas de réponse
        await session.port.requests.put({"kind": "public_chat", "state": state, "author": "imp", "text": "Bonjour"})
        await asyncio.sleep(0.01)
        assert session.pending is None
        task.cancel()

    asyncio.run(scenario())

    types = [m["type"] for m in sent]
    assert types == ["role_assigned", "game_state", "action_request", "game_state", "chat"]  # rôle une seule fois
    assert sent[2] == {"type": "action_request", "kind": "vote", "candidates": ["imp", "h"],
                       "max_targets": None, "min_targets": None, "role": None}
    assert sent[4] == {"type": "chat", "channel_id": "public", "sender": "imp", "content": "Bonjour"}
