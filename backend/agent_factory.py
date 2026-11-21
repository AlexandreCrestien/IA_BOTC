import logging
from typing import Optional
from pydantic import BaseModel, ValidationInfo, field_validator

from backend.llm_client import ask_llm, ask_llm_json
from backend.memory_manager import MemoryManager
from backend.prompt_loader import PromptLoader
from backend.models import Role
from backend.rules import Assignment

logger = logging.getLogger(__name__)


class Agent:
    """
    Agent IA d'un joueur : son identité fixe (id, nom, rôle), sa personnalité, son prompt système
    et la mémoire de la partie. L'état du joueur (vivant, effets…) n'est pas ici : il est dans GameState.
    """
    def __init__(self, player_id: str, name: str, role: Role, personality_key: str,
                 memory: MemoryManager, system_prompt: str):
        self.player_id = player_id
        self.name = name
        self.role = role
        # Personnalité = nom du fichier skill (ex. "agitator"). Interne : jamais montrée au joueur.
        self.personality_key = personality_key
        self.memory = memory
        self.system_prompt = system_prompt

    @property
    def role_name(self) -> str:
        return self.role.name_FR

    def _build_system_prompt(self) -> str:
        """Injecte dynamiquement la liste des joueurs présents, par leur nom, sans dupliquer le general_rules."""
        players = ", ".join(sorted(self.memory.name_of(pid) for pid in self.memory.player_ids))
        return f"{self.system_prompt.strip()}\n\n# CONTEXTE DE LA PARTIE\nJoueurs présents dans la partie : {players}."

    def _messages(self, instruction: str) -> list[dict]:
        context = self.memory.context_for(self.player_id)
        current_system_prompt = self._build_system_prompt()
        return [
            {"role": "system", "content": current_system_prompt},
            {"role": "user", "content": f"# CE QUE TU SAIS\n{context}\n\n# À TOI\n{instruction}"},
        ]

    async def speak_public(self, optional: bool = False) -> str | None:
        """Message pour le salon public.
        optional=True : l'agent peut passer son tour ; renvoie alors None."""
        instruction = (
            "C'est ton tour de parler dans le salon public. Écris un seul message court (2 phrases maximum), sans préfixe ni guillemets."
        )
        if optional:
            instruction += (
                " Tu n'es pas obligé de parler, et passer ton tour est un choix normal."
                " Ne parle que si tu apportes quelque chose de nouveau : un soupçon, une information,"
                " ou une réponse à quelqu'un qui s'adresse à toi."
                f" Sinon, réponds exactement : {PASS}"
            )
        text = await ask_llm("fast", self._messages(instruction))
        if optional and _is_pass(text):
            return None
        return text

    async def speak_private(self, partners: list[str], opening: bool = False) -> str:
        """Réponse dans une conversation privée. partners : ids des autres participants.
        opening=True : c'est l'agent qui a proposé l'entretien, il parle en premier."""
        names = ", ".join(self.memory.name_of(p) for p in partners)
        if opening:
            instruction = (
                f"Tu as proposé une conversation privée à {names}, qui a accepté. Ouvre la conversation par un seul message court (2 phrases maximum), sans préfixe ni guillemets."
            )
        else:
            instruction = (
                f"Tu es en conversation privée avec {names}. Réponds-leur par un seul message court (2 phrases maximum), sans préfixe ni guillemets."
            )
        return await ask_llm("fast", self._messages(instruction))

    async def night_action(self, options: list[str], number_of_targets: int = 1, situation: str = "") -> list[str]:
        """Choix de nuit selon le pouvoir du rôle."""
        if not options:
            raise ValueError("Aucune option légale fournie")
        prefix = f"{situation} " if situation else ""
        instruction = (
            f"{prefix}C'est la nuit. Utilise ton pouvoir : choisis {number_of_targets} joueur(s) parmi : {', '.join(options)}. Réponds uniquement en JSON : {{\"cibles\": [\"nom\", ...], \"raison\": \"pourquoi, en 5 mots maximum\"}}."
        )
        result = await ask_llm_json("capable", self._messages(instruction), NightAction,
                                     context={"options": options, "number_of_targets": number_of_targets})
        logger.info("%s (nuit) -> %s : %s", self.player_id, result.cibles, result.raison)
        return result.cibles

    async def vote(self, options: list[str]) -> str | None:
        """Vote pour un joueur à exécuter, ou None."""
        instruction = (
            f"Phase de jour. Veux-tu voter pour qu'un joueur soit exécuté ? Choix possibles : {', '.join(options)}, ou \"{NOBODY}\" si tu ne veux désigner personne pour l'instant. Réponds uniquement en JSON : {{\"cible\": \"nom\", \"raison\": \"pourquoi, en 5 mots maximum\"}}."
        )
        result = await ask_llm_json("capable", self._messages(instruction), Vote,
                                     context={"options": options + [NOBODY]})
        logger.info("%s (vote) -> %s : %s", self.player_id, result.cible, result.raison)
        return None if result.cible == NOBODY else result.cible

NOBODY = "Personne"
PASS = "PASSE"  # réponse d'un agent qui ne veut pas parler


def _is_pass(text: str) -> bool:
    """Vrai si la réponse est seulement PASSE, même avec ponctuation, guillemets ou gras (ex. "**Passe.**")."""
    return text.strip().strip(" .!*_\"'«»`").strip().upper() == PASS


def _check_in_options(name: str, info: ValidationInfo) -> str:
    options = (info.context or {})["options"]
    if name not in options:
        raise ValueError(f"{name!r} n'est pas un choix possible. Choix possibles : {', '.join(options)}")
    return name


class NightAction(BaseModel):
    cibles: list[str]
    raison: str

    @field_validator("cibles")
    @classmethod
    def _check_cibles(cls, cibles: list[str], info: ValidationInfo) -> list[str]:
        expected = (info.context or {})["number_of_targets"]
        if len(cibles) != expected:
            raise ValueError(f"Il faut exactement {expected} cible(s), pas {len(cibles)}")
        return [_check_in_options(c, info) for c in cibles]


class Vote(BaseModel):
    cible: str
    raison: str

    @field_validator("cible")
    @classmethod
    def _check_cible(cls, cible: str, info: ValidationInfo) -> str:
        return _check_in_options(cible, info)


class AgentFactory:
    """Assemble un Agent : rôle, personnalité, prompt système (skills) et mémoire de la partie."""
    def __init__(self, prompt_loader: Optional[PromptLoader] = None):
        self.prompt_loader = prompt_loader or PromptLoader()

    def create_agent(self, agent_id: str, name: str, role: Role, personality_key: str,
                     memory: MemoryManager) -> Agent:
        system_prompt = self.prompt_loader.assemble_system_prompt(
            role_name=role.name_EN,
            personality_name=personality_key,
            agent_name=name,
        )
        return Agent(agent_id, name, role, personality_key, memory, system_prompt)


def create_all_agents(assignments: dict[str, Assignment], memory: MemoryManager, human_id: str,
                      prompt_loader: Optional[PromptLoader] = None) -> dict[str, Agent]:
    """Crée un agent IA par joueur, sauf le joueur humain (human_id)."""
    if human_id not in assignments:
        raise ValueError(f"Le joueur humain {human_id} n'est pas dans la répartition")
    factory = AgentFactory(prompt_loader=prompt_loader)
    return {
        player_id: factory.create_agent(player_id, assignment.name, assignment.role,
                                        assignment.personality, memory)
        for player_id, assignment in assignments.items()
        if player_id != human_id
    }
