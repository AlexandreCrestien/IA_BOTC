import logging

from backend.agent_factory import Agent
from backend.memory_manager import MemoryManager
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
