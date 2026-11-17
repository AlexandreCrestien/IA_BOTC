from backend.front_state import to_front_state
from backend.memory_manager import MemoryManager, game_master
from backend.models import EventType, GameState, Player
from backend.models.enums import Equipe, Phase
from backend.models.role import Role

IMP = Role(name_FR="Diablotin", name_EN="imp", team=Equipe.DEMON, phase=Phase.NUIT)
PSYCHIC = Role(name_FR="Voyante", name_EN="psychic", team=Equipe.VILLAGEOIS, phase=Phase.NUIT)
VILLAGER = Role(name_FR="Villageois", name_EN="villager", team=Equipe.VILLAGEOIS)
NAMES = {"h": "Alex", "imp": "Imp", "mort": "Mort"}


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


def make_memory() -> MemoryManager:
    memory = MemoryManager(list(NAMES), names=NAMES)
    memory.set_moment(2, Phase.NUIT)
    memory.add_event(EventType.role_info, game_master, "Parmi Imp et Mort, aucun n'est un démon.", frozenset({"h"}))
    memory.add_public(EventType.public_message, "h", "Bonjour tout le monde.")
    memory.add_private(EventType.private_summary, "imp", "Bonjour.", {"h", "imp"})
    return memory


def test_phase_et_vivants():
    view = to_front_state(make_state(), make_memory(), "h")
    assert view["phase"] == "night"
    assert view["day"] == 2
    assert view["aliveCount"] == 2


def test_phase_de_discussion_sans_cible_de_nuit():
    view = to_front_state(make_state(Phase.DISCUSSION), make_memory(), "h")
    assert view["phase"] == "day"
    assert view["nightTargets"] == []
    assert view["nightCount"] == 0


def test_cibles_de_nuit_avec_nombre_exact_et_morts_inclus():
    view = to_front_state(make_state(), make_memory(), "h")
    assert view["nightCount"] == 2
    assert "mort" in {t["id"] for t in view["nightTargets"]}


def test_dernier_vote_par_joueur():
    history = ({"turn": 1, "votes": {"h": "imp", "imp": None}, "executed": None},)
    view = to_front_state(make_state(), make_memory(), "h", history)
    by_id = {p["id"]: p for p in view["players"]}
    assert by_id["h"]["lastVote"] == "Imp"
    assert by_id["imp"]["lastVote"] == "Personne"
    assert by_id["mort"]["lastVote"] is None


def test_messages_par_canal():
    view = to_front_state(make_state(), make_memory(), "h")
    assert view["messages"]["public"] == [{"sender": "Alex", "content": "Bonjour tout le monde."}]
    assert view["messages"]["whisper_h_imp"] == [{"sender": "Imp", "content": "Bonjour."}]


def test_historique_des_votes_en_noms():
    history = ({"turn": 1, "votes": {"h": "imp", "imp": None}, "executed": None},)
    view = to_front_state(make_state(), make_memory(), "h", history)
    assert view["votesHistory"] == [{"turn": 1, "votes": {"Alex": "Imp", "Imp": "Personne"}, "executed": None}]


def test_mort_avec_vote_fantome_peut_voter_sans_cibler_la_nuit():
    view = to_front_state(make_state(human_alive=False), make_memory(), "h")
    assert view["me"]["canVote"] is True
    assert view["nightTargets"] == []