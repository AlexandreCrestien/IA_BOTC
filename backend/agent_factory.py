from pathlib import Path

from backend.llm_client import ask_llm
from backend.memory_manager import MemoryManager

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
