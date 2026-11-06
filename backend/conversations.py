
import logging

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
