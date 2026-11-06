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
  - **Jour (minuté, 4 minutes) :** les IA ouvrent la discussion dans le salon public (10 messages au plus, dans un ordre fixé par leur personnalité). Ensuite, jusqu'à la fin du temps, l'humain peut :
    - écrire dans le salon public (les IA lui répondent) ;
    - ouvrir une conversation privée avec 1 ou 2 agents vivants (3 messages au plus). Pendant ce temps, les autres agents discutent entre eux en privé (échange simulé en un seul appel LLM, chacun note ce qu'il en retient). Le salon public garde la trace de qui parle avec qui ;
    - désigner un joueur (facultatif) : vote immédiat pour ou contre son exécution. Chacun désigne au plus une fois par jour, et un joueur n'est désigné qu'une fois par jour ;
    - finir sa journée.
  - À la moitié du temps, les IA peuvent désigner à leur tour, et si l'humain n'a parlé en privé avec personne, un agent lui propose une conversation.
  - **Vote sur une désignation :** chacun vote pour ou contre ; le joueur est exécuté si les « pour » sont plus de la moitié des joueurs vivants (égalité : personne). Un mort ne compte que s'il vote « pour ». S'il y a exécution, le jour s'arrête ; sinon, le jour continue.
  - **Vote de fin de jour :** si personne n'a été exécuté sur désignation, chacun choisit qui doit mourir (ou personne). Le joueur qui a plus de la moitié des votes exprimés est exécuté (égalité : personne).
  - Chaque étape attend la précédente : l'humain n'écrit jamais pendant qu'une IA répond.
- La première nuit, personne ne meurt. Le Diablotin et l'Empoisonneur apprennent qui est leur allié, et le Détective reçoit son information.
- Si un joueur (IA) fait un choix de nuit invalide ou n'en fait pas, un choix légal est tiré au hasard. Un vote pour un joueur mort ou inconnu compte comme une abstention.
- Les morts restent dans la partie : ils parlent encore et gardent un seul vote pour le reste de la partie (vote fantôme), utilisé quand ils votent pour l'exécution de quelqu'un (« contre » ou « personne » ne l'utilisent pas). Ils ne peuvent pas désigner.
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
| `ws://127.0.0.1:8000/ws/{pseudo}` | WebSocket du joueur : lance la partie et reçoit ses actions |
| `GET /admin/debug/all-states` | Débogage, protégé par le header `x-admin-token` : parties en cours avec les rôles, effets et personnalités de tous les joueurs, et l'historique complet (qui pouvait voir quoi) |

Actions envoyées par le navigateur (JSON) : `start_game`, `send_chat`, `create_channel`, `nominate`, `night_action`, `vote`, `pass`.
Messages envoyés par le serveur : `state` (tour, phase, joueurs, rôle de l'humain), `event` (message ou annonce visible par l'humain), `request` (le moteur attend une action : `night`, `day` avec la fin du jour, une éventuelle proposition d'un agent et les joueurs que l'humain peut désigner, `private_message`, `vote` sur une désignation, `final_vote` en fin de jour), `wait` (le moteur n'attend plus d'action), `game_over`, `error`. Le lien entre le moteur et le WebSocket est fait par `backend/server/game_session.py`.

## Interface web

Ouvrir `http://127.0.0.1:8000/` une fois le serveur lancé. L'interface (`static/index.html`, `static/js/app.js`, `static/css/style.css`, avec Tailwind CSS) contient :

- un écran d'accueil où le joueur choisit son pseudo, qui sert d'identifiant pour la connexion WebSocket ;
- une table ronde avec les joueurs vivants et morts ;
- un chat par salon (public et privés), avec des onglets pour l'historique des nuits et des votes ;
- un minuteur du jour dans la barre du haut ;
- un panneau d'actions qui change selon la phase : choix de nuit ; le jour, conversation privée, désignation facultative et « Finir ma journée » ; vote pour ou contre une désignation ; vote de fin de jour ;
- la liste des joueurs, avec une note de soupçon pour chacun ;
- des fenêtres pour la révélation du rôle, la proposition de conversation d'un agent et la fin de partie (rôles de tous les joueurs, bouton « Rejouer »).

Déroulement côté joueur : le pseudo lance une partie contre les 5 IA. Le panneau d'actions affiche ce que le moteur attend ; le reste du temps, les IA réfléchissent et leurs messages arrivent au fur et à mesure.

## Jouer dans le terminal

Deux scripts lancent une partie avec les vrais modèles (clés d'API nécessaires, appels payants et plus lents) :

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
- Tours avec les IA (`ai_turns.py`) et avec l'humain (`human_turns.py`) : choix de nuit, réponse de la Voyante, jour minuté, désignation facultative (vote pour ou contre), vote de fin de jour
- Conversations privées entre agents pendant le salon privé de l'humain (simulées en un appel LLM)
- Un agent propose une conversation à l'humain qui n'a parlé en privé avec personne
- Annonces publiques des morts de la nuit, des désignations, des votes et de l'exécution, enregistrées dans la mémoire des agents
- Interface web (`static/`) reliée au moteur par le WebSocket : une partie complète se joue dans le navigateur
- Route admin : état caché et historique complet des parties en cours
- Parties dans le terminal (`scripts/`)

## Documentation

- [`docs/architecture_ia.md`](docs/architecture_ia.md) : fonctionnement de `llm_client`, `memory_manager`, `agent_factory` et `conversations`
- [`docs/choix_des_modeles.md`](docs/choix_des_modeles.md) : choix des modèles LLM et leurs résultats aux tests
