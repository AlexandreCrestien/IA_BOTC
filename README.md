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

Provocateur, Parano, Bouffon, Stratège et Observateur (fichiers dans `skills/personalities/`). Chaque agent IA reçoit une personnalité différente, tirée au hasard ; l'humain n'en a pas.

### Déroulement

- Chaque tour enchaîne trois phases : **nuit → discussion → vote**.
  - **Nuit :** les IA puis l'humain font leur choix de nuit ; les morts de la nuit sont annoncés. La Voyante reçoit la réponse de son sondage.
  - **Discussion :** les IA parlent dans le salon public (10 messages au plus, dans un ordre fixé par leur personnalité), puis l'humain peut écrire un message public. Il peut ensuite ouvrir un salon privé avec 1 ou 2 agents vivants (3 messages au plus).
  - **Vote :** les IA puis l'humain votent. Chaque étape attend la précédente : l'humain n'écrit jamais pendant qu'une IA répond.
- La première nuit, personne ne meurt. Le Diablotin et l'Empoisonneur apprennent qui est leur allié, et le Détective reçoit son information.
- Si un joueur (IA) fait un choix de nuit invalide ou n'en fait pas, un choix légal est tiré au hasard. Un vote pour un joueur mort ou inconnu compte comme une abstention.
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
├── rules/             Règles : distribution des rôles et personnalités, actions légales, nuit, vote, Majordome, victoire
├── server/            Serveur FastAPI : WebSocket, route admin, schémas des messages
├── llm_client.py      Seul accès aux LLM (profils "fast" et "capable", fallback, réponses JSON)
├── memory_manager.py  Ce que chaque joueur sait (événements publics, privés, personnels)
├── agent_factory.py   Création des agents IA et leurs actions (parler, agir la nuit, voter)
├── conversations.py   Phases de conversation publique et privée
├── prompt_loader.py   Assemblage du prompt des agents à partir des skills
├── game_engine.py     Boucle de jeu : mise en place de la partie, nuit, vote, tours jusqu'à la victoire
├── ai_turns.py        Tour joué par les IA (choix de nuit, discussion, votes)
└── human_turns.py     Tour avec l'humain et les IA (HumanPort : interface entre le moteur et l'humain)
static/                Interface web (HTML, CSS, JS), servie par FastAPI
skills/                Textes des prompts : règles générales, rôles, personnalités
scripts/               Parties avec les vrais modèles, dans le terminal
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
| `GET /` | Interface web (fichiers de `static/`) |
| `GET /health` | Vérifie que le serveur tourne |
| `GET /docs` | Documentation automatique de l'API (FastAPI) |
| `ws://127.0.0.1:8000/ws/{player_id}` | WebSocket du joueur : reçoit et valide ses actions |
| `GET /admin/debug/all-states` | Route de débogage, protégée par le header `x-admin-token` |

Actions acceptées sur le WebSocket (JSON) : `send_chat`, `create_channel`, `night_action`, `vote`.

## Interface web

Ouvrir `http://127.0.0.1:8000/` une fois le serveur lancé. L'interface (`static/index.html`, `static/js/app.js`, `static/css/style.css`, avec Tailwind CSS) contient :

- un écran d'accueil où le joueur choisit son pseudo, qui sert d'identifiant pour la connexion WebSocket ;
- une table ronde avec les joueurs vivants et morts ;
- un chat par salon (public et privés), avec des onglets pour l'historique des nuits et des votes ;
- un panneau d'actions qui change selon la phase (discussion, vote, nuit) ;
- la liste des joueurs, avec une note de soupçon pour chacun ;
- des fenêtres pour la révélation du rôle, la demande de conversation d'un agent et la fin de partie.

C'est une première version : elle n'est pas encore reliée au moteur de jeu.

## Jouer dans le terminal

En attendant que l'interface soit reliée au moteur, deux scripts lancent une partie avec les vrais modèles (clés d'API nécessaires, appels payants et plus lents) :

```bash
python scripts/play_with_human.py   # tu joues contre les 5 IA : tu tapes tes choix
python scripts/play_real_game.py    # les IA jouent seules ; l'humain reçoit des choix aléatoires
```

## Tests

```bash
python -m pytest tests/ -q
```

Les tests n'appellent jamais de vrai LLM : ils utilisent un faux LLM. À lancer depuis la racine du projet.

## État d'avancement

**Fait :**
- Modèles de la partie et règles (distribution, actions de nuit, poison, protection, meurtre, vote, Majordome, victoire)
- Client LLM avec bascule entre modèles
- Mémoire par joueur (avec les noms des joueurs, datée par le moteur) et agents IA
- Phases de conversation publique et privée
- Serveur : WebSocket, validation des actions, route admin
- Boucle de jeu (`game_engine.py`) : mise en place (rôles, personnalités, fausse piste de la Voyante, agents, infos de première nuit), tours nuit → vote, arrêt à la victoire
- Tours avec les IA (`ai_turns.py`) et avec l'humain (`human_turns.py`) : choix de nuit, réponse de la Voyante, discussion publique, salon privé, votes
- Première version de l'interface web (`static/`) : écrans et affichage, pas encore reliés au moteur
- Parties dans le terminal (`scripts/`)

**À faire :**
- Enregistrer dans la mémoire des agents les morts de la nuit, les votes et l'exécution (aujourd'hui, seul l'humain est prévenu des morts)
- Quand l'humain n'ouvre pas de salon privé, faire venir un agent vers lui (`choose_agent_for_human` existe mais n'est pas encore appelée)
- Relier le moteur au serveur et à l'interface (actions de l'humain reçues par le WebSocket, envoi de l'état). Les types de messages utilisés par l'interface ne sont pas encore ceux de `backend/server/schemas.py` : à aligner
- Contenu de la route admin (en attente du moteur de jeu)

## Documentation

- [`docs/architecture_ia.md`](docs/architecture_ia.md) : fonctionnement de `llm_client`, `memory_manager`, `agent_factory` et `conversations`
- [`docs/choix_des_modeles.md`](docs/choix_des_modeles.md) : choix des modèles LLM et leurs résultats aux tests
