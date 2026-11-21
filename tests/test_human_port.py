import asyncio

from backend.human_port import QueueHumanPort
from backend.models import GameState, Player
from backend.models.enums import Equipe, Phase
from backend.models.role import Role

IMP = Role(name_FR="Diablotin", name_EN="imp", team=Equipe.DEMON, phase=Phase.NUIT)
PSYCHIC = Role(name_FR="Voyante", name_EN="psychic", team=Equipe.VILLAGEOIS, phase=Phase.NUIT)
VILLAGER = Role(name_FR="Villageois", name_EN="villager", team=Equipe.VILLAGEOIS)


def make_state() -> GameState:
    """Le joueur humain est la Voyante. Un Diablotin vivant, et un villageois mort."""
    return GameState(
        turn=2,
        phase=Phase.NUIT,
        players=(
            Player(id="h", name="Alex", role=PSYCHIC),
            Player(id="imp", name="Imp", role=IMP),
            Player(id="mort", name="Mort", role=VILLAGER, alive=False, ghost_vote=True),
        ),
    )


async def answer_with(port: QueueHumanPort, reply):
    """Le « serveur » : lit la demande du moteur et renvoie la réponse prévue."""
    request = await port.requests.get()
    await port.answers.put(reply)
    return request


def run_with_server(port: QueueHumanPort, reply, action):
    """Lance une action du moteur, puis répond une fois à sa demande."""
    async def main():
        server = asyncio.create_task(answer_with(port, reply))
        result = await action()
        request = await server
        return result, request
    return asyncio.run(main())


def test_night_choice_envoie_cibles_et_nombre_puis_recoit_la_reponse():
    port = QueueHumanPort()
    state = make_state()
    result, request = run_with_server(port, ["imp", "mort"], lambda: port.night_choice(state, "h"))
    assert result == ("imp", "mort")
    assert request["kind"] == "night_choice"
    assert request["count"] == 2
    assert "mort" in request["targets"]  # on peut toujours cibler un mort


def test_vote_ne_propose_que_les_vivants():
    port = QueueHumanPort()
    state = make_state()
    result, request = run_with_server(port, "imp", lambda: port.vote(state, "h"))
    assert result == "imp"
    assert request["kind"] == "vote"
    assert request["targets"] == ["h", "imp"]


def test_partenaires_privés_excluent_soi_mais_pas_les_morts():
    port = QueueHumanPort()
    state = make_state()
    result, request = run_with_server(port, ["mort"], lambda: port.private_partners(state, "h"))
    assert result == ["mort"]
    assert request["choices"] == ["imp", "mort"]


def test_annonce_de_mort_ne_bloque_pas_le_moteur():
    port = QueueHumanPort()
    state = make_state()

    async def main():
        await port.show_night_deaths(state, ("mort",))  # ne doit pas attendre de réponse
        return await port.requests.get()

    request = asyncio.run(main())
    assert request == {"kind": "night_deaths", "state": state, "deaths": ["mort"]}


def test_chaque_demande_transmet_l_etat_courant():
    port = QueueHumanPort()
    state = make_state()
    _, request = run_with_server(port, None, lambda: port.public_message(state, "h"))
    assert request["state"] is state