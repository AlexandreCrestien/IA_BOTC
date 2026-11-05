# 🕰️ Blood on the AI Clocktower

Création d'un site pour jouer contre des IA à *Blood on the Clocktower*.

> **Projet en cours de développement.** Ce README décrit l'état actuel du code ; il sera complété au fil du projet.

## Le jeu

Une partie se joue à **6 joueurs** : un humain et **5 agents IA**. Chaque agent reçoit un rôle secret et une personnalité, et parle grâce à un LLM.

### Rôles

| Rôle | Camp | Pouvoir |
|---|---|---|
| 😈 Diablotin | Démon | Chaque nuit, choisit un habitant à tuer. |
| 🧪 Empoisonneur | Sbire | Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante. |
| 🛡️ Moine | Villageois | Chaque nuit, protège un habitant de l'attaque du diablotin. |
| 🔮 Voyante | Villageois | Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie. |
| 🔍 Détective | Villageois | Au début de la partie, voit un sbire parmi deux joueurs, dont l'un est choisi au hasard. |
| 🎩 Majordome | Outsider | Chaque nuit, choisit un maître. Ne peut voter que si son maître vote aussi. |

### Personnalités des agents

Provocateur, Parano, Bouffon, Stratège et Observateur (fichiers dans `skills/personalities/`).

### Déroulement

- Chaque tour enchaîne trois phases : **nuit → discussion → vote**.
- La première nuit, personne ne meurt.
- Les morts restent dans la partie et gardent un dernier vote (vote fantôme).
- **Victoire :** le bien gagne si le Diablotin meurt ; le mal gagne s'il ne reste aucun joueur du bien vivant.

## Stack technique

- **Python** (3.12 ou plus)
- **FastAPI** + **Uvicorn** : serveur HTTP et WebSocket
- **Pydantic** : modèles de données et validation
- **LiteLLM** : accès aux LLM (Groq, Gemini, OpenRouter), avec bascule automatique vers un autre modèle en cas d'échec
- **pytest** : tests

## Structure du projet

```
backend/
├── models/            État de la partie : joueurs, rôles, effets, salons, journal (GameState, Player, Role…)
├── rules/             Règles : distribution des rôles, actions légales, nuit, vote, Majordome, victoire
├── server/            Serveur FastAPI : WebSocket, route admin, schémas des messages
├── llm_client.py      Seul accès aux LLM (profils "fast" et "capable", fallback, réponses JSON)
├── memory_manager.py  Ce que chaque joueur sait (événements publics, privés, personnels)
├── agent_factory.py   Création des agents IA et leurs actions (parler, agir la nuit, voter)
├── conversations.py   Phases de conversation publique et privée
├── prompt_loader.py   Assemblage du prompt des agents à partir des skills
└── game_engine.py     Boucle de jeu (à faire)
skills/                Textes des prompts : règles générales, rôles, personnalités
frontend/              Interface web (à faire)
docs/                  Documentation technique
tests/                 Tests unitaires
main.py                Lance le serveur
```

## Installation

```bash
git clone https://github.com/AlexandreCrestien/IA_BOTC.git
cd IA_BOTC
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copier `.env.example` en `.env`, puis remplir les clés :

| Variable | Rôle |
|---|---|
| `GROQ_API_KEY` | Clé API Groq |
| `GEMINI_API_KEY` | Clé API Gemini (Google AI Studio) |
| `OPENROUTER_API_KEY` | Clé API OpenRouter |
| `ADMIN_SECRET_TOKEN` | Jeton de la route `/admin`. Vide = admin fermé. Pour en générer un : `python -c "import secrets; print(secrets.token_hex(32))"` |

Le fichier `.env` ne doit jamais être commité.

## Lancer le serveur

```bash
python main.py
```

Le serveur démarre sur `http://127.0.0.1:8000` :

| Adresse | Rôle |
|---|---|
| `GET /health` | Vérifie que le serveur tourne |
| `GET /docs` | Documentation automatique de l'API (FastAPI) |
| `ws://127.0.0.1:8000/ws/{player_id}` | WebSocket du joueur : reçoit et valide ses actions |
| `GET /admin/debug/all-states` | Route de débogage, protégée par le header `x-admin-token` |

Actions acceptées sur le WebSocket (JSON) : `send_chat`, `create_channel`, `night_action`, `vote`.

## Tests

```bash
python -m pytest tests/ -q
```

Les tests n'appellent jamais de vrai LLM : ils utilisent un faux LLM. À lancer depuis la racine du projet.

## État d'avancement

**Fait :**
- Modèles de la partie et règles (distribution, actions de nuit, poison, protection, meurtre, vote, Majordome, victoire)
- Client LLM avec bascule entre modèles
- Mémoire par joueur et agents IA
- Phases de conversation publique et privée
- Serveur : WebSocket, validation des actions, route admin

**À faire :**
- Boucle de jeu (`game_engine.py`) : relier les règles, les agents et le serveur
- Interface web (`frontend/`)
- Contenu de la route admin (en attente du moteur de jeu)

## Documentation

- [`docs/architecture_ia.md`](docs/architecture_ia.md) : fonctionnement de `llm_client`, `memory_manager`, `agent_factory` et `conversations`
- [`docs/choix_des_modeles.md`](docs/choix_des_modeles.md) : choix des modèles LLM et leurs résultats aux tests
