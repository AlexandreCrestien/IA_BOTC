
import logging

from pydantic import BaseModel, ValidationInfo, field_validator

from backend import llm_client
from backend.agent_factory import Agent
from backend.memory_manager import MemoryManager, game_master
from backend.models import EventType

logger = logging.getLogger(__name__)

MAX_PUBLIC_MESSAGES = 10

# Ordre de parole et obligation de parler, par personnalité (clé = nom du fichier skill).
personalities = [
    {"personality": "agitator", "order": 1, "is_obliged": True},
    {"personality": "paranoid", "order": 2, "is_obliged": True},
    {"personality": "clown", "order": 3, "is_obliged": True},
    {"personality": "strategist", "order": 4, "is_obliged": False},
    {"personality": "observer", "order": 5, "is_obliged": False},
]

# Personnalité absente du tableau : parle en dernier, sans obligation.
DEFAULT_RULE = {"order": 99, "is_obliged": False}


def _rule_for(agent: Agent) -> dict:
    """Retrouve la ligne du tableau correspondant à la personnalité de l'agent."""
    for rule in personalities:
        if agent.personality_key == rule["personality"]:
            return rule
    return DEFAULT_RULE


async def public_conversation(agents: list[Agent], memory: MemoryManager,
                              max_messages: int = MAX_PUBLIC_MESSAGES) -> list[tuple[str, str]]:
    """Phase de conversation publique entre les agents IA (l'humain n'est pas dans `agents`).

    Les agents parlent à tour de rôle dans l'ordre des personnalités, jusqu'à max_messages au total.
    Les personnalités non obligées peuvent passer leur tour.
    Chaque message est enregistré tout de suite dans la mémoire, pour que le suivant le voie.

    Renvoie la liste des messages (id_joueur, texte), dans l'ordre, pour l'affichage.
    """
    speakers = sorted(agents, key=lambda agent: _rule_for(agent)["order"])
    said: list[tuple[str, str]] = []

    while len(said) < max_messages:
        said_this_round = 0
        for agent in speakers:
            if len(said) >= max_messages:
                break
            try:
                text = await agent.speak_public(optional=not _rule_for(agent)["is_obliged"])
            except Exception:
                # Filet de sécurité : si le LLM échoue, l'agent ne parle pas et la partie continue.
                logger.exception("%s n'a pas pu parler", agent.player_id)
                continue
            if text is None:
                logger.info("%s passe son tour", agent.player_id)
                continue
            memory.add_public(EventType.public_message, agent.player_id, text)
            said.append((agent.player_id, text))
            said_this_round += 1
        if said_this_round == 0:
            break  # tout le monde a passé (ou échoué) : la discussion est finie

    return said


# Conversation privée

def choose_agent_for_human(agents: list[Agent], human_id: str, memory: MemoryManager) -> Agent:
    """Choisit l'agent qui va proposer une conversation privée à l'humain (quand l'humain n'a choisi personne).

    Priorité aux agents qui n'ont jamais discuté en privé avec l'humain ;
    parmi eux, la personnalité la plus bavarde (ordre du tableau).
    """
    if not agents:
        raise ValueError("Aucun agent disponible pour une conversation privée")
    already_talked = memory.private_partners(human_id)
    candidates = [a for a in agents if a.player_id not in already_talked] or agents
    return min(candidates, key=lambda agent: _rule_for(agent)["order"])


def _check_partners(human_id: str, partners: list[Agent]) -> None:
    if not 1 <= len(partners) <= 2:
        raise ValueError(f"Une conversation privée se fait avec 1 ou 2 agents, pas {len(partners)}")
    if any(agent.player_id == human_id for agent in partners):
        raise ValueError("L'humain ne peut pas être son propre interlocuteur")


async def _replies(human_id: str, partners: list[Agent], memory: MemoryManager) -> list[tuple[str, str]]:
    """Chaque agent de la conversation répond à son tour. Chaque réponse est enregistrée tout de suite,
    pour que le second agent voie la réponse du premier."""
    participants = {human_id} | {agent.player_id for agent in partners}
    said: list[tuple[str, str]] = []
    for agent in partners:
        others = sorted(participants - {agent.player_id})
        try:
            text = await agent.speak_private(others)
        except Exception:
            # Filet de sécurité : l'agent ne répond pas, la conversation continue.
            logger.exception("%s n'a pas pu répondre en privé", agent.player_id)
            continue
        memory.add_private(EventType.private_summary, agent.player_id, text, participants)
        said.append((agent.player_id, text))
    return said


async def start_private_conversation(human_id: str, partners: list[Agent], memory: MemoryManager,
                                     agent_speaks_first: bool = False) -> list[tuple[str, str]]:
    """Ouvre une conversation privée entre l'humain et 1 ou 2 agents.

    Annonce publiquement que la conversation a lieu (sans son contenu).
    agent_speaks_first=True : l'agent ouvre la conversation (cas où l'humain n'a choisi personne).
    Renvoie les messages des agents (id_joueur, texte), vide si l'humain parle en premier.
    """
    _check_partners(human_id, partners)
    names = ", ".join(memory.name_of(p) for p in [human_id] + [agent.player_id for agent in partners])
    memory.add_public(EventType.private_meeting, game_master, f"Conversation privée entre {names}.")
    if agent_speaks_first:
        return await _replies(human_id, partners, memory)
    return []


async def private_message(human_id: str, text: str, partners: list[Agent],
                          memory: MemoryManager) -> list[tuple[str, str]]:
    """L'humain envoie un message dans sa conversation privée ; chaque agent lui répond.

    Appelé par le serveur à chaque message de l'humain.
    Renvoie les réponses des agents (id_joueur, texte), pour l'affichage.
    """
    _check_partners(human_id, partners)
    participants = {human_id} | {agent.player_id for agent in partners}
    memory.add_private(EventType.private_summary, human_id, text, participants)
    return await _replies(human_id, partners, memory)


# --- Conversation privée simulée entre agents ----------------------------------------
# Pendant que l'humain parle en privé, les autres agents discutent entre eux. Pour limiter
# les appels, l'échange entier est simulé en un seul appel LLM, qui donne aussi ce que
# chaque agent retient (sa note personnelle).

MAX_SIMULATED_LINES = 6


class SimulatedLine(BaseModel):
    auteur: str
    message: str

    @field_validator("auteur")
    @classmethod
    def _known_author(cls, auteur: str, info: ValidationInfo) -> str:
        names = (info.context or {})["names"]
        if auteur not in names:
            raise ValueError(f"{auteur!r} ne participe pas. Participants : {', '.join(names)}")
        return auteur


class SimulatedConversation(BaseModel):
    echange: list[SimulatedLine]
    notes: dict[str, str]

    @field_validator("notes")
    @classmethod
    def _one_note_each(cls, notes: dict[str, str], info: ValidationInfo) -> dict[str, str]:
        names = set((info.context or {})["names"])
        if set(notes) != names:
            raise ValueError(f"Il faut une note pour chaque participant : {', '.join(sorted(names))}")
        return notes


def _simulation_messages(agents: list[Agent], memory: MemoryManager) -> list[dict]:
    profiles = []
    for agent in agents:
        profiles.append(
            f"## {agent.name}\n"
            f"Rôle secret : {agent.role_name}. Personnalité : {agent.personality}.\n"
            f"Ce que {agent.name} sait :\n{memory.context_for(agent.player_id)}"
        )
    names = ", ".join(agent.name for agent in agents)
    system = (
        "Tu es le narrateur d'une partie de Blood on the Clocktower (variante du loup-garou). "
        "Tu simules une courte conversation privée et secrète entre des joueurs. "
        "Chaque joueur ne connaît que ses propres informations : il peut mentir ou cacher son rôle "
        "s'il est du côté du mal, et il ne doit jamais révéler ce qu'il ne sait pas. "
        "Les messages sont courts (1 ou 2 phrases), en français, fidèles à la personnalité de chacun."
    )
    user = (
        "\n\n".join(profiles)
        + f"\n\n# À TOI\nSimule leur conversation privée ({MAX_SIMULATED_LINES} messages au plus), "
        + f"puis écris pour chacun ce qu'il retient (une phrase, de son point de vue). "
        + 'Réponds uniquement en JSON : {"echange": [{"auteur": "nom", "message": "..."}], '
        + '"notes": {"nom": "ce qu\'il retient"}}. '
        + f"Participants : {names}."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def simulate_agents_conversation(agents: list[Agent], memory: MemoryManager) -> list[tuple[str, str]]:
    """Conversation privée entre 2 agents ou plus, simulée en un seul appel LLM.

    Annonce publique « Conversation privée entre … » (sans le contenu) ; chaque message est
    enregistré en privé pour les participants, et la note de chaque agent dans sa mémoire personnelle.
    Renvoie les messages (id_joueur, texte). En cas d'échec du LLM, rien n'est enregistré
    à part l'annonce."""
    if len(agents) < 2:
        return []
    by_name = {agent.name: agent for agent in agents}
    participants = {agent.player_id for agent in agents}
    names = ", ".join(agent.name for agent in agents)
    memory.add_public(EventType.private_meeting, game_master, f"Conversation privée entre {names}.")
    try:
        result = await llm_client.ask_llm_json(
            "capable", _simulation_messages(agents, memory), SimulatedConversation,
            context={"names": list(by_name)},
        )
    except Exception:
        logger.exception("La conversation simulée entre %s a échoué", names)
        return []

    said = []
    for line in result.echange[:MAX_SIMULATED_LINES]:
        author = by_name[line.auteur]
        memory.add_private(EventType.private_summary, author.player_id, line.message, participants)
        said.append((author.player_id, line.message))
    for name, note in result.notes.items():
        agent = by_name[name]
        memory.add_personal(EventType.private_summary, game_master,
                            f"Ce que tu retiens de ta conversation privée : {note}", agent.player_id)
    return said
