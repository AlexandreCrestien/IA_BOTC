import asyncio

from backend.engine.human_port import QueueHumanPort
from backend.models import GameState, Player
from backend.models.enums import Phase
from backend.rules import get_role

IMP = get_role("imp")
PSYCHIC = get_role("psychic")
VILLAGER = get_role("detective")  # villageois sans action de nuit


def make_state() -> GameState:
    """Le joueur humain est la Voyante. Un Diablotin vivant, et un villageois mort."""
    return GameState(
        turn=2,
        phase=Phase.NIGHT,
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


def test_night_choice_sends_targets_and_count_then_gets_the_answer():
    port = QueueHumanPort()
    state = make_state()
    result, request = run_with_server(port, ["imp", "mort"], lambda: port.night_choice(state, "h"))
    assert result == ("imp", "mort")
    assert request["kind"] == "night_choice"
    assert request["count"] == 2
    assert "mort" in request["targets"]  # on peut toujours cibler un mort


def test_vote_offers_only_living_players_except_oneself():
    port = QueueHumanPort()
    state = make_state()
    result, request = run_with_server(port, "imp", lambda: port.vote(state, "h"))
    assert result == "imp"
    assert request["kind"] == "vote"
    assert request["targets"] == ["imp"]  # ni soi-même, ni le mort


def test_private_partners_exclude_oneself_but_not_the_dead():
    port = QueueHumanPort()
    state = make_state()
    result, request = run_with_server(port, ["mort"], lambda: port.private_partners(state, "h"))
    assert result == ["mort"]
    assert request["choices"] == ["imp", "mort"]


def test_death_announcement_does_not_block_the_engine():
    port = QueueHumanPort()
    state = make_state()

    async def main():
        await port.show_night_deaths(state, ("mort",))  # ne doit pas attendre de réponse
        return await port.requests.get()

    request = asyncio.run(main())
    assert request == {"kind": "night_deaths", "state": state, "deaths": ["mort"]}


def test_each_request_carries_the_current_state():
    port = QueueHumanPort()
    state = make_state()
    _, request = run_with_server(port, None, lambda: port.public_message(state, "h"))
    assert request["state"] is state