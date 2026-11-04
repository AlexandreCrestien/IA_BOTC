import logging
from typing import Optional
from pydantic import BaseModel, ValidationInfo, field_validator

from backend.llm_client import ask_llm, ask_llm_json
from backend.memory_manager import MemoryManager
from backend.prompt_loader import PromptLoader
from backend.models import Joueur, Role

logger = logging.getLogger(__name__)


class Agent:
    """
    Représente un agent IA complet pour le jeu, combinant :
    - L'état de jeu officiel (le Joueur et son Role de models.py)
    - La couche IA et comportementale (le system_prompt généré par le PromptLoader, la mémoire et les actions)
    """
    def __init__(self, player: Joueur, personality: str, memory: MemoryManager, system_prompt: str):
        self.player = player
        self.personality = personality
        self.memory = memory
        self.system_prompt = system_prompt

    @property
    def player_id(self) -> str:
        return self.player.id

    @property
    def name(self) -> str:
        return self.player.nom

    @property
    def role_name(self) -> str:
        return self.player.role.nom

    def _build_system_prompt(self) -> str:
        """Injecte dynamiquement la liste des joueurs vivants/présents sans dupliquer le general_rules."""
        players = ", ".join(sorted(self.memory.player_ids))
        return f"{self.system_prompt.strip()}\n\n# CONTEXTE DE LA PARTIE\nJoueurs présents dans la partie : {players}."

    def _messages(self, instruction: str) -> list[dict]:
        context = self.memory.context_for(self.player_id)
        current_system_prompt = self._build_system_prompt()
        return [
            {"role": "system", "content": current_system_prompt},
            {"role": "user", "content": f"# CE QUE TU SAIS\n{context}\n\n# À TOI\n{instruction}"},
        ]

    async def speak_public(self) -> str:
        """Message pour le salon public."""
        instruction = (
            "C'est ton tour de parler dans le salon public. Écris un seul message court (2 phrases maximum), sans préfixe ni guillemets."
        )
        return await ask_llm("fast", self._messages(instruction))

    async def speak_private(self, partners: list[str]) -> str:
        """Réponse dans une conversation privée."""
        instruction = (
            f"Tu es en conversation privée avec {', '.join(partners)}. Réponds-leur par un seul message court (2 phrases maximum), sans préfixe ni guillemets."
        )
        return await ask_llm("fast", self._messages(instruction))

    async def night_action(self, options: list[str], number_of_targets: int = 1) -> list[str]:
        """Choix de nuit selon le pouvoir du rôle."""
        if not options:
            raise ValueError("Aucune option légale fournie")
        instruction = (
            f"C'est la nuit. Utilise ton pouvoir : choisis {number_of_targets} joueur(s) parmi : {', '.join(options)}. Réponds uniquement en JSON : {'cibles': ['nom', ...], 'raison': 'pourquoi, en 5 mots maximum'}."
        )
        result = await ask_llm_json("capable", self._messages(instruction), NightAction,
                                     context={"options": options, "number_of_targets": number_of_targets})
        logger.info("%s (nuit) -> %s : %s", self.player_id, result.cibles, result.raison)
        return result.cibles

    async def vote(self, options: list[str]) -> str | None:
        """Vote pour un joueur à exécuter, ou None."""
        instruction = (
            f"Phase de jour. Veux-tu voter pour qu'un joueur soit exécuté ? Choix possibles : {', '.join(options)}, ou \"{NOBODY}\" si tu ne veux désigner personne pour l'instant. Réponds uniquement en JSON : {'cible': 'nom', 'raison': 'pourquoi, en 5 mots maximum'}."
        )
        result = await ask_llm_json("capable", self._messages(instruction), Vote,
                                     context={"options": options + [NOBODY]})
        logger.info("%s (nomination) -> %s : %s", self.player_id, result.cible, result.raison)
        return None if result.cible == NOBODY else result.cible

NOBODY = "Personne"


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
    """
    Fabrique qui assemble l'Agent, le PromptLoader et les modèles Pydantic officiels.
    """
    def __init__(self, prompt_loader: Optional[PromptLoader] = None):
        self.prompt_loader = prompt_loader or PromptLoader()

    def create_agent(self, agent_id: str, agent_name: str, role_data: dict, personality_data: dict, memory: MemoryManager) -> Agent:
        """
        Crée un agent prêt à jouer en combinant le rôle, le joueur, les assets markdown et la mémoire de partie.
        """
        role_obj = Role(**role_data)

        player_obj = Joueur(
            id=agent_id,
            nom=agent_name,
            role=role_obj
        )

        role_file = role_obj.nom_EN
        personality_file = personality_data["personality_name_EN"]
        personality_display_name = personality_data.get("personality_name_FR", personality_file)

        system_prompt = self.prompt_loader.assemble_system_prompt(
            role_name=role_file,
            personality_name=personality_file,
            agent_name=agent_name
        )

        return Agent(
            player=player_obj,
            personality=personality_display_name,
            memory=memory,
            system_prompt=system_prompt
        )


# !! A déplacer dans un fichier qui gère le déroulement du jeu

def create_all_agents(assignments: dict[str, tuple[str, dict, dict]], memory: MemoryManager, human_id: str, prompt_loader: Optional[PromptLoader] = None) -> dict[str, Agent]:
    """
    Initialise tous les agents IA de la partie à partir d'un dictionnaire d'affectations.
    assignments : {id_joueur: (nom_du_joueur, role_data, personality_data)}
    L'humain (human_id) est exclu des agents IA générés.
    """
    if human_id not in assignments:
        raise ValueError(f"Le joueur humain {human_id} n'est pas dans la répartition")
        
    factory = AgentFactory(prompt_loader=prompt_loader)
    agents = {}
    
    for player_id, (agent_name, role_data, personality_data) in assignments.items():
        if player_id == human_id:
            continue
            
        agent = factory.create_agent(
            agent_id=player_id,
            agent_name=agent_name,
            role_data=role_data,
            personality_data=personality_data,
            memory=memory
        )
        agents[player_id] = agent
        
    return agents