# 🏮 Lantern Hollow

Jeu de déduction sociale, variante du loup-garou : un joueur humain affronte seul cinq personnages pilotés par des IA, chacun avec sa personnalité.

> **Projet en cours de développement.** Ce README décrit l'état actuel du code ; il sera complété au fil du projet.

## Le jeu

Une partie se joue à **6 joueurs** : un humain et **5 agents IA**. Chaque agent reçoit un rôle secret et une personnalité, et parle grâce à un LLM.

### Rôles

| Rôle | Camp | Pouvoir |
|---|---|---|
| 😈 Faucheur | Démon | Chaque nuit, choisit un habitant à tuer. |
| 🧪 Apothicaire | Complice | Chaque nuit, empoisonne un habitant. Le poison dure jusqu'à la fin de la journée suivante. |
| 🛡️ Veilleur | Villageois | Chaque nuit, protège un habitant de l'attaque du Faucheur. |
| 🔮 Médium | Villageois | Chaque nuit, sonde deux joueurs et apprend si l'un d'eux est démon. Une fausse piste est choisie au début de la partie. |
| 🔍 Inquisiteur | Villageois | Au début de la partie, voit un complice parmi deux joueurs, dont l'un est choisi au hasard. |
| 🎩 Valet | Paria | Chaque nuit, choisit un maître. Ne peut voter que si son maître vote aussi. |

### Personnalités des agents

Provocateur, Parano, Bouffon, Stratège et Observateur (fichiers dans `skills/personalities/`). Chaque agent IA reçoit une personnalité différente, tirée au hasard ; l'humain n'en a pas.

### Déroulement

- Chaque tour enchaîne trois phases : **nuit → discussion → vote**.
  - **Nuit :** les IA puis l'humain font leur choix de nuit ; les morts de la nuit sont annoncés. Le Médium reçoit la réponse de son sondage.
  - **Discussion :** les IA parlent dans le salon public (10 messages au plus, dans un ordre fixé par leur personnalité), puis l'humain peut écrire un message public. Il peut ensuite ouvrir un salon privé avec 1 ou 2 agents, vivants ou morts (3 messages au plus), ou passer directement au vote. S'il ne choisit rien pendant 10 secondes, un agent vient lui proposer un entretien.
  - **Conversations entre agents :** pendant le salon privé de l'humain, deux autres agents s'entretiennent en privé. La conversation n'est pas jouée : un seul appel au LLM en écrit un résumé pour chacun des deux. Leur entretien est annoncé sur la place publique, ce qui donne un indice au joueur.
  - **Vote :** les IA puis l'humain votent. Chaque étape attend la précédente : l'humain n'écrit jamais pendant qu'une IA répond.
- La première nuit, personne ne meurt. Le Faucheur et l'Apothicaire apprennent qui est leur allié, et l'Inquisiteur reçoit son information.
- Si un joueur (IA) fait un choix de nuit invalide ou n'en fait pas, un choix légal est tiré au hasard. Personne ne peut voter contre soi-même ; un vote pour soi, pour un joueur mort ou inconnu compte comme une abstention.
- Les morts restent dans la partie : ils parlent toujours et gardent un dernier vote, leur voix d'outre-tombe.
- Tout le monde, IA comprises, apprend les morts de la nuit, les votes de chacun et les exécutions. Les informations de rôle (Médium, Inquisiteur, alliés du mal) restent personnelles.
- **Victoire :** le bien gagne si le Faucheur meurt ; le mal gagne s'il ne reste plus aucun joueur du bien en vie, ou s'il n'en reste qu'un seul après le vote (le Faucheur le tuerait la nuit suivante, la partie s'arrête là).

### Comptes, statistiques et succès

- **Invité ou compte.** On peut jouer en invité (pseudo seul, rien n'est enregistré) ou avec un compte (pseudo et mot de passe). Un invité qui crée un compte, ou se connecte, pendant la partie ou sur l'écran de fin, y rattache la partie en cours.
- **Tableau de bord** (joueur connecté) : lancer, reprendre ou abandonner sa partie ; statistiques ; historique des parties ; succès ; changement de pseudo et de mot de passe.
- **Statistiques :** parties jouées, part de victoires (au total, côté villageois, côté démons), nombre moyen de tours. Un abandon compte comme une défaite ; une partie interrompue par le serveur (arrêt, plantage) ne compte pas.
- **Fermer l'onglet ne termine pas la partie :** elle attend le joueur, qui la reprend ou l'abandonne depuis l'accueil ou le tableau de bord.
- **Succès** (14), calculés à la fin d'une partie gagnée ou perdue (pas d'un abandon) :

| Succès | Condition | Visible |
|---|---|---|
| Victoire : Faucheur, Apothicaire, Veilleur, Médium, Inquisiteur, Valet | Gagner une partie avec ce rôle | oui |
| Voix d'outre-tombe | Utiliser sa voix d'outre-tombe | oui |
| Bourreau | Voter pour un joueur qui est exécuté | oui |
| Sur l'échafaud | Être exécuté | oui |
| Expéditif | Gagner en 3 tours ou moins | oui |
| Coup de maître | Gagner en un seul tour (seul le bien le peut : exécuter le Faucheur au premier vote) | caché |
| Premier sacrifié | Être exécuté au premier tour | caché |
| Revenant | Gagner en ayant été exécuté | caché |
| Increvable | Gagner en ayant été tué par le Faucheur | caché |

Un succès caché s'affiche « ??? » tant qu'il n'est pas débloqué. Titres et messages : `backend/stats/achievements.py`.

## Stack technique

- **Python** (3.12 ou plus)
- **FastAPI** + **Uvicorn** : serveur HTTP et WebSocket
- **Pydantic** : modèles de données et validation
- **SQLAlchemy** + **SQLite** : comptes, parties jouées et succès (fichier `data/lantern_hollow.db`)
- **bcrypt** (mots de passe) et **PyJWT** (jeton de connexion, dans un cookie `HttpOnly`)
- **LiteLLM** : accès aux LLM (Groq, Gemini, OpenRouter), avec bascule automatique vers un autre modèle en cas d'échec
- **pytest** et **Playwright** : tests

## Structure du projet

```
backend/
├── models/            État de la partie : joueurs, rôles, effets, événements (GameState, Player, Role, RoleKey…)
├── rules/             Règles : catalogue et distribution des rôles, actions légales, nuit, vote, Valet, victoire
├── server/            Serveur FastAPI (voir docs/protocol.md)
│   ├── session.py         La partie en cours (une seule à la fois) et ce que le serveur en retient
│   ├── game_runner.py     Lancement, reprise, abandon, et qui peut rejoindre quelle partie
│   ├── game_records.py    Enregistrement de la partie pour le compte du joueur, succès de fin de partie
│   ├── websocket_endpoint.py, protocol.py, schemas.py   WebSocket : actions du front et messages du serveur
│   ├── auth.py            Routes /api/auth et /api/account : inscription, connexion (cookie), profil
│   ├── game_routes.py     Routes /api/game : partie en cours, abandon depuis le tableau de bord
│   ├── stats_routes.py    Routes /api/me : statistiques, historique, succès
│   └── admin.py           Routes /admin : état complet de la partie, comptes (réservées au compte admin)
├── accounts/          Comptes : règles du pseudo, mots de passe (bcrypt), jetons (JWT), opérations sur les comptes
├── db/                Base de données (SQLAlchemy) : tables des comptes, parties et succès ; ouverture au démarrage
├── stats/             Succès (définitions, conditions) et statistiques d'un compte
├── engine/            Moteur de jeu
│   ├── setup.py           Mise en place : rôles, personnalités, fausse piste, agents, infos de première nuit
│   ├── steps.py           Étapes du tour : nuit, vote, morts, réponse du Médium, annonces publiques
│   ├── turn.py            Le tour de jeu (seule boucle) ; HumanPort : interface entre le moteur et l'humain
│   ├── human_port.py      Ports de l'humain : WebSocket (QueueHumanPort), joueur automatique (AutoHumanPort)
│   └── config.py          Noms des agents IA et personnalités
└── ai/                Agents IA
    ├── llm_client.py      Seul accès aux LLM (profils "fast" et "capable", fallback, réponses JSON)
    ├── prompt_loader.py   Assemblage du prompt des agents à partir des skills
    ├── memory_manager.py  Ce que chaque joueur sait (événements publics, privés, personnels)
    ├── agent.py           Agents IA et leurs actions (parler, agir la nuit, voter)
    ├── choices.py         Choix de nuit et votes des agents, demandés ensemble
    ├── conversations.py   Phases de conversation publique et privée
    └── agent_whispers.py  Conversation simulée entre deux agents (tirage du duo, résumés)
static/                Interface web servie par FastAPI : jeu (index.html), tableau de bord (dashboard.html),
                       administration (admin.html), page introuvable (not-found.html)
skills/                Textes des prompts : règles générales, rôles, personnalités
scripts/               Parties dans le terminal, simulations et test complet
docs/                  Documentation technique
tests/                 Tests, rangés comme le code : models, rules, engine, ai, server, frontend (Playwright), integration
data/                  Base SQLite, créée au premier démarrage (ignorée par git)
main.py                Lance le serveur
pyproject.toml         Configuration de pytest et ruff
```

## Installation

```bash
git clone https://github.com/AlexandreCrestien/IA_BOTC.git
cd IA_BOTC
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # navigateur des tests du frontend
```

Copier `.env.example` en `.env`, puis remplir les clés :

| Variable | Rôle |
|---|---|
| `GROQ_API_KEY` | Clé API Groq |
| `GEMINI_API_KEY` | Clé API Gemini (Google AI Studio) |
| `OPENROUTER_API_KEY` | Clé API OpenRouter |
| `JWT_SECRET` | Clé qui signe les jetons de connexion. Absente : clé temporaire, les joueurs sont déconnectés à chaque redémarrage |
| `ADMIN_PSEUDO`, `ADMIN_PASSWORD` | Compte administrateur, créé au premier démarrage s'il n'existe pas (mot de passe : 8 caractères au moins). Absents : pas de compte admin, panneau fermé |
| `DATABASE_URL` | Facultatif. Adresse de la base, par défaut `sqlite:///data/lantern_hollow.db` |

`JWT_SECRET` doit être une **longue chaîne aléatoire** (au moins 32 caractères), jamais un mot ou une phrase : qui la connaît peut se faire passer pour n'importe quel compte, admin compris. Pour en obtenir une, lancer une fois dans le terminal l'une de ces commandes et coller le résultat dans `.env` :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
openssl rand -hex 32
```

Le fichier `.env` ne doit jamais être commité.

## Lancer le serveur

```bash
python main.py
```

Le serveur démarre sur `http://127.0.0.1:8000` :

| Adresse | Rôle |
|---|---|
| `GET /` | Interface web : accueil et jeu (fichiers de `static/`) |
| `GET /dashboard.html` | Tableau de bord du joueur connecté |
| `GET /health` | Vérifie que le serveur tourne |
| `GET /docs` | Documentation automatique de l'API (FastAPI) |
| `ws://<serveur>/ws/{pseudo}` | WebSocket du joueur : lance ou reprend sa partie, reçoit et valide ses actions |
| `/api/auth/*`, `/api/account/*` | Inscription, connexion, déconnexion, profil |
| `/api/game/*` | Partie en cours, abandon depuis le tableau de bord |
| `/api/me/*` | Statistiques, historique des parties, succès |
| `GET /admin` | Page d'administration (développeurs) |
| `/admin/*` | Données de la page d'administration, réservées au compte admin |

Une adresse inconnue affiche la page 404 du jeu ; les routes de l'API gardent leurs réponses JSON. Détail des routes, des actions du front et des messages du serveur : [`docs/protocol.md`](docs/protocol.md).

## Interface web

Ouvrir `http://127.0.0.1:8000/`, puis jouer en invité (un pseudo suffit), se connecter ou créer un compte. Une seule partie à la fois sur le serveur. L'interface (`static/index.html`, `static/js/`, `static/css/style.css`, avec Tailwind CSS) contient :

- une table ronde et la liste des joueurs, avec une note de soupçon pour chacun ;
- un chat par salon (public et privés), avec des onglets pour l'historique des nuits et des votes ;
- un panneau d'actions qui change selon la phase (discussion, vote, nuit) ;
- des fenêtres pour le rôle, le réveil du village, la proposition d'entretien d'un agent et la fin de partie ;
- un menu : tableau de bord (nouvel onglet) et déconnexion pour un joueur connecté, création de compte ou connexion pour un invité, abandon de la partie. Après un rechargement de la page, la partie reprend où elle en était ;
- une fenêtre de fin de partie avec les succès débloqués (ou, pour un invité, la proposition de créer un compte pour garder la partie) ;
- un Codex (rôles, règles, et un onglet « IA & données » : le joueur sait qu'il joue contre des IA, quelles données sont envoyées et à qui) ;
- une annonce quand l'IA d'un personnage ne répond pas (sauf la nuit, pour ne rien révéler de son rôle).

Le tableau de bord (`static/dashboard.html`, `static/js/dashboard.js`) a des raccourcis vers ses sections : statistiques et historique, succès, profil.

La page d'administration (`http://127.0.0.1:8000/admin`) demande le compte admin (`ADMIN_PSEUDO` / `ADMIN_PASSWORD` du `.env`). Elle montre :
- la partie présente sur le serveur (en cours, ou la dernière terminée), sans rien cacher : rôles, personnalités, historique public et historique personnel de chaque agent, actions de nuit, votes, IA indisponibles ;
- la liste des comptes, avec un bouton pour réinitialiser le mot de passe d'un joueur qui l'a oublié (mot de passe temporaire affiché une seule fois, à lui transmettre).

## Scripts

À lancer depuis la racine du projet. Les trois premiers appellent les vrais modèles (clés d'API nécessaires, plus lents) :

```bash
python scripts/play_with_human.py   # tu joues contre les 5 IA dans le terminal
python scripts/play_ai_game.py      # les IA jouent seules (le 6e joueur s'abstient et ne parle pas)
python scripts/check_nights.py      # les IA jouent seulement des nuits : contrôle de leurs cibles
python scripts/simulate_game.py     # partie simulée, sans LLM : affiche chaque message reçu par le front
python scripts/check_full_game.py   # partie simulée, sans LLM, avec des centaines de vérifications
```

`scripts/recording.py` est un module utilitaire (historiques des joueurs pour `play_with_human.py`), pas un script à lancer.

**Mode simulation** : avec `SIMULATE_LLM=1`, aucun appel aux modèles (réponses fictives tirées parmi les choix légaux). Pratique pour essayer l'interface sans clé ni quota :

```bash
SIMULATE_LLM=1 python main.py
```

## Tests

```bash
python -m pytest tests/ -q                     # tout (backend + frontend)
python -m pytest tests/ -q --ignore=tests/frontend   # backend seul
python -m pytest tests/frontend -q             # frontend seul (ajouter --headed pour voir le navigateur)
```

Les tests n'appellent jamais de vrai LLM : ils utilisent de faux agents, ou le mode simulation. Ils n'utilisent jamais la vraie base : chaque test a sa base SQLite en mémoire (`tests/conftest.py`), et le compte admin du `.env` est ignoré. `tests/integration/test_full_game.py` joue des parties complètes avec `scripts/check_full_game.py`. À lancer depuis la racine du projet.

Les tests du frontend (`tests/frontend/`) pilotent un vrai navigateur avec Playwright. Ils ne demandent ni serveur lancé ni connexion internet : le dossier `static/` est servi localement, et le serveur (WebSocket et routes `/api`) est simulé.

Vérification du code (erreurs réelles uniquement, sans reformatage) :

```bash
ruff check .
```

## État d'avancement

**Fait :**
- Règles des six rôles (distribution, actions de nuit, poison, protection, meurtre, vote, Valet, victoire)
- Agents IA : client LLM avec bascule entre modèles, mémoire publique et personnelle, personnalités, conversations publiques et privées, conversations simulées entre agents
- Tour de jeu unique (`backend/engine/turn.py`), utilisé par le serveur, le terminal, les scripts et les tests
- Serveur : WebSocket (une partie à la fois, reprise après rechargement, abandon), page et routes d'administration
- Interface web reliée au moteur, et parties dans le terminal
- Comptes (invité ou compte, connexion par cookie), tableau de bord, statistiques, historique des parties, succès ; compte admin et réinitialisation des mots de passe
- Page 404

**À faire :**
- Résumer la mémoire des agents au fil des jours : le contexte grandit à chaque événement (voir les limites connues dans `docs/ai_architecture.md`)
- Mise en production : Tailwind est chargé depuis son CDN, à compiler pour la production ; le cookie de connexion est à passer en `Secure` derrière HTTPS (`backend/server/auth.py`)

## Axes d'amélioration

- **PostgreSQL et Alembic** : remplacer SQLite par PostgreSQL et faire évoluer le schéma par migrations (aujourd'hui, les tables sont créées au démarrage). Le code passe par SQLAlchemy : il suffit surtout de changer `DATABASE_URL` et le driver.
- **Docker** : `docker-compose` avec le serveur et la base.
- **Adresse e-mail** : connexion par e-mail, mot de passe oublié par lien envoyé par e-mail (aujourd'hui, l'admin réinitialise le mot de passe).
- **Suppression du compte** par le joueur lui-même (aujourd'hui, ni le joueur ni l'admin ne peuvent supprimer un compte).
- **Une partie par joueur** : aujourd'hui une seule partie à la fois sur le serveur (une session globale), ce qui suffit en local. Il faudrait une session par joueur, et des messages publics limités à leur partie.
- **Historique détaillé des parties dans le panel admin** : choisir un joueur, puis une de ses parties passées, et en voir tout le détail (chat, votes, nuits, mémoire des IA). Il faudrait enregistrer en base, à la fin de chaque partie, ce que le panel montre de la partie en cours (un bloc JSON par partie).

## Documentation

- [`docs/ai_architecture.md`](docs/ai_architecture.md) : fonctionnement des agents IA (`backend/ai/`) et du tour de jeu
- [`docs/model_choices.md`](docs/model_choices.md) : choix des modèles LLM et leurs résultats aux tests
- [`docs/protocol.md`](docs/protocol.md) : messages échangés entre le front et le serveur (WebSocket)
