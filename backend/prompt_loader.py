from pathlib import Path
from typing import Union

class PromptLoader:
    def __init__(self, base_dir: Union[str, Path, None] = None):
        """
        Initialise le loader en pointant vers le dossier skills si aucun dossier n'est fourni en paramètre.
        """
        if base_dir is None:
            self.base_dir = Path(__file__).resolve().parent.parent / "skills"
        else:
            self.base_dir = Path(base_dir)

        self.roles_dir = self.base_dir / "roles"
        self.personalities_dir = self.base_dir / "personalities"
        self.general_rules_file = self.base_dir / "general_rules.md"


    def personality_display_name(self, personality_name: str) -> str:
        """Nom affiché (français) d'une personnalité, lu dans son skill
        (ligne « Nom de la personnalité : … »). Renvoie la clé si le fichier ou la ligne manque."""
        path = self.personalities_dir / f"{personality_name.strip().lower()}.md"
        if not path.exists():
            return personality_name
        for line in path.read_text(encoding="utf-8").splitlines():
            if "Nom de la personnalité" in line and ":" in line:
                name = line.split(":", 1)[1].strip().strip("*").strip()
                if name:
                    return name
        return personality_name

    def _read_markdown_file(self, file_path: Path) -> str:
        """Lit un fichier Markdown de manière sécurisée."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found : {file_path.resolve()}")
        return file_path.read_text(encoding="utf-8").strip()


    def assemble_system_prompt(self, role_name: str, personality_name: str, agent_name: str = "plAIyer") -> str:
        """
        Assemble le system prompt dans un ordre logique optimisé pour le LLM :
        1. Contexte & objectif
        2. Rôle de joueur
        3. Personnalité
        4. Règles et contraintes strictes
        """

        role_name = role_name.strip().lower()
        personality_name = personality_name.strip().lower()

        general_rules = self._read_markdown_file(self.general_rules_file)
        role_content = self._read_markdown_file(self.roles_dir / f"{role_name}.md")
        personality_content = self._read_markdown_file(self.personalities_dir / f"{personality_name}.md")

        system_prompt = f"""
# CONTEXTE ET OBJECTIF
Tu participes à une partie de jeu de rôle et de déduction sociale inspirée du loup-garou : "Blood on the Clocktower". 
Ton nom dans cette partie est {agent_name}. 

**Fonctionnement global du jeu :**
- La partie alterne entre des **phases de nuit** (où les personnages agissent en secret, et où le Diablotin peut éliminer quelqu'un) et des **phases de jour** (où les habitants du village débattent publiquement, s'analysent et votent pour exécuter un suspect).
- Ton objectif suprême est de faire gagner ton camp : les Villageois (gentils) ou les Démons (méchants). Pour cela tu dois survivre, enquêter et manipuler les autres.
---

# TON RÔLE DE JOUEUR
{role_content}

---

# TA PERSONNALITÉ ET TON STYLE DE JEU
{personality_content}

---

# RÈGLES ET CONTRAINTES STRICTES
{general_rules}
        """

        return system_prompt