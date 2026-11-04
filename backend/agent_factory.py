import logging
from pathlib import Path
from pydantic import BaseModel, ValidationInfo, field_validator

from backend.llm_client import ask_llm, ask_llm_json
from backend.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


# TODO(Flora) : TEMPORAIRE. À remplacer par le skill_loader quand il sera prêt.
# Lecture directe des fichiers .md en attendant.
def _load_skill_temporary(folder: str, name: str) -> str:
    return (SKILLS_DIR / folder / f"{name}.md").read_text(encoding="utf-8")


GAME_RULES = """Tu joues à un jeu de société de déduction sociale inspiré de Blood on the Clocktower.
C'est un jeu : mentir, bluffer et accuser font partie des règles, personne n'est réellement en danger.

## Règles
- Deux camps : les Démons (le Diablotin et son sbire) et les Villageois.
- La nuit, certains rôles utilisent leur pouvoir en secret. Le jour, tout le monde discute puis peut voter pour exécuter un joueur.
- La première nuit, personne ne meurt jamais : c'est la règle, ce n'est pas un indice.
- Les morts restent dans la partie : ils perdent leur pouvoir mais continuent à discuter.

## Ce que tu sais
- Tu ne connais que ce qui figure dans ton historique. N'invente jamais d'événements, de tentatives ou d'informations.
- Ce que tu as appris en privé est secret : ne le répète en public que si c'est un choix stratégique.
- Si tu es un Démon, tu connais ton allié, mais tu ne dois jamais le montrer : pas d'allusion à son rôle, pas de « nous » qui trahirait votre camp. En public, traite-le comme n'importe quel autre joueur.

## Style
- Réponds toujours en français, à la première personne, comme un joueur autour de la table.
- Messages courts : 3 phrases maximum.
- Pas de hashtags, d'emojis, de titres ni de mise en forme : seulement ce que tu dirais à voix haute."""


class Agent:
    def __init__(self, player_id: str, role: str, personality: str, memory: MemoryManager):
        self.player_id = player_id
        self.role = role
        self.personality = personality
        self.memory = memory
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        players = ", ".join(sorted(self.memory.player_ids))
        return "\n\n".join([
            GAME_RULES,
            f"Ton nom dans la partie : {self.player_id}. Joueurs présents : {players}.",
            "# TON RÔLE (secret)\n" + _load_skill_temporary("roles", self.role),
            "# TA PERSONNALITÉ\n" + _load_skill_temporary("personalities", self.personality),
        ])

    def _messages(self, instruction: str) -> list[dict]:
        context = self.memory.context_for(self.player_id)
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"# CE QUE TU SAIS\n{context}\n\n# À TOI\n{instruction}"},
        ]

    async def speak_public(self) -> str:
        """Message pour le salon public. L'orchestrateur l'enregistre ensuite dans la mémoire."""
        instruction = (
            "C'est ton tour de parler dans le salon public. "
            "Écris un seul message court (1 à 3 phrases), sans préfixe ni guillemets."
        )
        return await ask_llm("fast", self._messages(instruction))

    async def speak_private(self, partners: list[str]) -> str:
        """Réponse dans une conversation privée. Les messages de la conversation doivent déjà
        être dans la mémoire (événements privés enregistrés par l'orchestrateur)."""
        instruction = (
            f"Tu es en conversation privée avec {', '.join(partners)}. "
            "Réponds-leur par un seul message court (1 à 3 phrases), sans préfixe ni guillemets."
        )
        return await ask_llm("fast", self._messages(instruction))

    async def night_action(self, options: list[str], number_of_targets: int = 1) -> list[str]:
        """Choix de nuit selon le pouvoir du rôle (décrit dans son skill).

        options : les cibles légales, fournies par le moteur de règles.
        number_of_targets : 2 pour la Voyante, 1 pour les autres.
        """
        if not options:
            raise ValueError("Aucune option légale fournie")
        instruction = (
            f"C'est la nuit. Utilise ton pouvoir : choisis {number_of_targets} joueur(s) parmi : {', '.join(options)}. "
            'Réponds uniquement en JSON : {"cibles": ["nom", ...], "raison": "pourquoi, en une phrase"}.'
        )
        result = await ask_llm_json("capable", self._messages(instruction), NightAction,
                                    context={"options": options, "number_of_targets": number_of_targets})
        logger.info("%s (nuit) -> %s : %s", self.player_id, result.cibles, result.raison)
        return result.cibles

    async def nominate(self, options: list[str]) -> str | None:
        """Désigne un joueur à exécuter, ou None pour ne désigner personne."""
        instruction = (
            f"Phase de jour. Veux-tu désigner un joueur pour qu'il soit exécuté ? Choix possibles : {', '.join(options)}, "
            f"ou \"{NOBODY}\" si tu ne veux désigner personne pour l'instant. "
            'Réponds uniquement en JSON : {"cible": "nom", "raison": "pourquoi, en une phrase"}.'
        )
        result = await ask_llm_json("capable", self._messages(instruction), Nomination,
                                    context={"options": options + [NOBODY]})
        logger.info("%s (nomination) -> %s : %s", self.player_id, result.cible, result.raison)
        return None if result.cible == NOBODY else result.cible

    async def vote(self, nominee: str) -> bool:
        """Vote pour (True) ou contre (False) l'exécution du joueur désigné."""
        instruction = (
            f"{nominee} a été désigné pour être exécuté. Votes-tu pour son exécution ? "
            'Réponds uniquement en JSON : {"vote": true ou false, "raison": "pourquoi, en une phrase"}.'
        )
        result = await ask_llm_json("capable", self._messages(instruction), Vote)
        logger.info("%s (vote contre %s) -> %s : %s", self.player_id, nominee, result.vote, result.raison)
        return result.vote


NOBODY = "personne"


def _check_in_options(name: str, info: ValidationInfo) -> str:
    """Refuse un nom qui n'est pas dans les options légales (passées via context)."""
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


class Nomination(BaseModel):
    cible: str
    raison: str

    @field_validator("cible")
    @classmethod
    def _check_cible(cls, cible: str, info: ValidationInfo) -> str:
        return _check_in_options(cible, info)


class Vote(BaseModel):
    vote: bool
    raison: str


def create_agents(assignments: dict[str, tuple[str, str]], memory: MemoryManager, human_id: str) -> dict[str, Agent]:
    """Crée un agent par joueur IA. assignments : {id_joueur: (rôle, personnalité)}, humain compris.

    L'humain n'a pas d'agent : il reçoit seulement son rôle.
    """
    if human_id not in assignments:
        raise ValueError(f"Le joueur humain {human_id} n'est pas dans la répartition")
    return {
        player_id: Agent(player_id, role, personality, memory)
        for player_id, (role, personality) in assignments.items()
        if player_id != human_id
    }
