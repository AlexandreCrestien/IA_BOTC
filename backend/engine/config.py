"""Composition de la partie : les 5 agents IA (identifiant -> nom affiché) et leurs personnalités.
Utilisé par le serveur (game_runner) et par les scripts de partie en terminal."""

AI_NAMES = {
    "p1": "marIA",
    "p2": "tobIAs",
    "p3": "mAIsie",
    "p4": "adrIAn",
    "p5": "dIAne",
}

# Clés des fichiers skills/personalities/<clé>.md, une par agent IA
PERSONALITY_NAMES = ["agitator", "clown", "observer", "paranoid", "strategist"]
