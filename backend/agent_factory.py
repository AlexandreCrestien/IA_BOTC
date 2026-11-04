from typing import Optional
from backend.prompt_loader import PromptLoader
from backend.models import Joueur, Role

class LLMAgent:
    """
    Représente un agent IA complet pour le jeu, combinant :
    - L'état de jeu officiel (le Joueur et son Role de models.py)
    - La couche IA (le system_prompt généré par le PromptLoader et sa personnalité)
    """
    def __init__(self, player: Joueur, personality: str, system_prompt: str):
        self.player = player
        self.personality = personality
        self.system_prompt = system_prompt

    @property
    def name(self) -> str:
        return self.player.nom

    @property
    def role_name(self) -> str:
        return self.player.role.nom


class AgentFactory:
    """
    Fabrique qui assemble le LLMAgent, le PromptLoader et les modèles Pydantic pour créer un agent.
    """
    def __init__(self, prompt_loader: Optional[PromptLoader] = None):
        self.prompt_loader = prompt_loader or PromptLoader()

    def create_agent(self, agent_id: str, agent_name: str, role_data: dict, personality_data: dict) -> LLMAgent:
        """
        Crée un agent prêt à jouer en combinant le rôle, le joueur et le system prompt.
        """
        role_obj = Role(**role_data)

        player_obj = Joueur(
            id=agent_id,
            nom=agent_name,
            role=role_obj
        )

        # !! Ajouter l'attribut nom_EN au modèle + transmettre un dict personality_data avec noms FR et EN 
        role_file = role_obj.nom_EN
        personality_file = personality_data["personality_name_EN"]
        personality_display_name = personality_data.get("personality_name_FR", personality_file)

        system_prompt = self.prompt_loader.assemble_system_prompt(
            role_name=role_file,
            personality_name=personality_file,
            agent_name=agent_name
        )

        return LLMAgent(
            player=player_obj,
            personality=personality_display_name,
            system_prompt=system_prompt
        )
