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

- **Invité ou compte.** On peut jouer en invité (pseudo seul, rien n'est enregistré) ou avec un compte (pseudo, adresse e-mail et mot de passe ; connexion avec le pseudo ou l'adresse). L'adresse doit être **confirmée** par le lien reçu à l'inscription (valable 24 heures) avant d'accéder au tableau de bord ou de lancer une partie avec le compte ; un compte non confirmé sous 72 heures est supprimé. Un changement d'adresse se confirme de la même façon, l'ancienne restant active jusque-là. Un invité qui crée un compte, ou se connecte, pendant la partie ou sur l'écran de fin, y rattache la partie en cours.
- **Tableau de bord** (joueur connecté) : lancer, reprendre ou abandonner sa partie ; statistiques ; historique des parties ; succès ; changement de pseudo, d'adresse e-mail et de mot de passe ; export de ses données (fichier JSON : profil, parties, succès, statistiques) ; suppression du compte.
- **Mot de passe oublié** : depuis l'accueil, un lien est envoyé par e-mail, seulement à une adresse confirmée (usage unique, valable 30 minutes) vers la page `reset-password.html`. La réponse est la même que l'adresse ait un compte ou non, et les demandes sont limitées à 3 par adresse en 15 minutes.
- **Suppression d'un compte**, la même par le joueur (tableau de bord, mot de passe demandé), par l'admin, ou automatiquement après **un an sans connexion**, un mois après un e-mail d'avertissement : le compte (pseudo, adresse e-mail, mot de passe), ses succès, le détail de ses parties et le registre de ses modifications sont effacés ; le résumé de ses parties est gardé de façon anonyme (détaché du compte, daté au jour près) pour les statistiques du jeu. Sa partie en cours est arrêtée. Le compte admin ne peut pas être supprimé.
- **Statistiques :** parties jouées, part de victoires (au total, côté villageois, côté démons), nombre moyen de tours. Un abandon compte comme une défaite ; une partie interrompue par le serveur (arrêt, plantage) ne compte pas.
- **Comparaison aux autres joueurs** (à partir de 10 joueurs, sinon une moyenne désigne presque quelqu'un) : sous chaque statistique, la moyenne de tous les joueurs (▲ / ▼ selon qu'on fait mieux ou moins bien), et sous chaque succès, la part des joueurs qui l'ont débloqué. Moyennes calculées par partie, y compris les parties anonymisées des comptes supprimés ; comptes admin exclus.
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
- **PostgreSQL** (lancé avec **Docker Compose**), **SQLAlchemy** et **Alembic** (migrations) : comptes, parties jouées et succès. Sans Docker, le jeu peut utiliser un fichier **SQLite** à la place
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
│   └── migrations/        Migrations Alembic (versions/ : une migration par changement du schéma)
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
                       administration (admin.html), nouveau mot de passe (reset-password.html),
                       confirmation de l'adresse (verify-email.html),
                       page introuvable (not-found.html)
skills/                Textes des prompts : règles générales, rôles, personnalités
scripts/               Parties dans le terminal, simulations et test complet
docs/                  Documentation technique
tests/                 Tests, rangés comme le code : models, rules, engine, ai, server, frontend (Playwright), integration
docker/                Script de création de la base des tests (exécuté par PostgreSQL au premier démarrage)
data/                  Base SQLite, seulement sans Docker (ignorée par git)
main.py                Lance le serveur
docker-compose.yml     Base PostgreSQL locale
alembic.ini            Configuration des migrations
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
cp .env.example .env                    # puis remplir les clés (voir ci-dessous)
```

Docker (avec Docker Compose) doit être installé. Il fait tourner, accessibles depuis cet ordinateur seulement :
- la base **PostgreSQL** (`127.0.0.1:5432`) ;
- **Mailpit**, un faux serveur d'e-mails : il capture les e-mails envoyés par le jeu sans rien envoyer pour de vrai, et les affiche sur **http://localhost:8025**.

## Lancer le jeu

**La première fois** (ou après avoir arrêté la base), deux commandes :

```bash
docker compose up -d   # 1. démarrer la base PostgreSQL et Mailpit (en arrière-plan)
python main.py         # 2. démarrer le serveur du jeu
```

**Les fois suivantes, une seule commande suffit** : la base reste lancée en arrière-plan, et Docker la redémarre tout seul, même après un redémarrage de l'ordinateur, tant qu'elle n'a pas été arrêtée.

```bash
python main.py
```

Si la base n'est pas lancée, `python main.py` s'arrête aussitôt avec ce message : « Base de données injoignable… lancez-la : `docker compose up -d` ».

**Arrêter :** `Ctrl+C` arrête le serveur du jeu. Pour arrêter aussi la base :

```bash
docker compose down    # arrêter la base (les comptes, parties et succès sont gardés)
docker compose ps      # vérifier si la base tourne
```

Les données sont gardées dans un volume Docker : `docker compose down` puis `docker compose up -d` les retrouve. Seul `docker compose down -v` les efface définitivement.

## Base de données et migrations

Au démarrage, le serveur applique les **migrations** Alembic : la première fois, il crée toutes les tables. Après un changement de `backend/db/models.py`, créer la migration correspondante puis la relire :

```bash
alembic revision --autogenerate -m "description du changement"
alembic upgrade head      # l'appliquer sans attendre le redémarrage du serveur
alembic current           # version de la base
```

**Sans Docker :** laisser `DATABASE_URL` vide dans `.env`. Le jeu utilise alors un fichier SQLite (`data/lantern_hollow.db`), créé au premier démarrage. Une base SQLite créée par une version du jeu antérieure aux migrations est refusée avec un message clair : il suffit de la supprimer.

## E-mails

Le jeu envoie quatre sortes d'e-mails : le lien de confirmation de l'adresse, le lien « mot de passe oublié », les notifications de sécurité (adresse remplacée, envoyée à l'ancienne adresse ; mot de passe modifié ou réinitialisé), avec l'adresse à contacter si la modification ne vient pas du joueur, et l'avertissement un mois avant la suppression d'un compte inactif. En dehors du lien de confirmation, rien n'est envoyé à une adresse non confirmée. Rien ne part vers une vraie boîte mail en local :
- **`MAIL_MODE=console`** (par défaut, sans rien installer) : l'e-mail s'affiche dans la console du serveur ; on y copie le lien ;
- **`MAIL_MODE=smtp`** : l'e-mail est envoyé à **Mailpit** (lancé par `docker compose up -d`) et s'affiche sur **http://localhost:8025**, comme dans une vraie boîte de réception.

Textes des e-mails : `backend/accounts/emails.py` ; envoi : `backend/mail.py`.

Côté RGPD : la raison de la collecte de l'adresse est expliquée là où elle est demandée (icône « ? » à côté du champ), les adresses sont masquées dans les journaux du serveur (`z***@exemple.fr`, sauf en mode `console`, fait pour le développement), et les liens « mot de passe oublié » expirés sont effacés chaque jour.

## Variables d'environnement

Le fichier `.env.example`, copié en `.env` à l'installation, contient toutes les variables :

| Variable | Rôle |
|---|---|
| `GROQ_API_KEY` | Clé API Groq |
| `GEMINI_API_KEY` | Clé API Gemini (Google AI Studio) |
| `OPENROUTER_API_KEY` | Clé API OpenRouter |
| `JWT_SECRET` | Clé qui signe les jetons de connexion. Absente : clé temporaire, les joueurs sont déconnectés à chaque redémarrage |
| `ADMIN_PSEUDO`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | Compte administrateur, créé au premier démarrage s'il n'existe pas (mot de passe : 8 caractères au moins ; adresse facultative). Absents : pas de compte admin, panneau fermé |
| `CONTACT_EMAIL` | Adresse à contacter, indiquée dans les e-mails de sécurité (à défaut : `ADMIN_EMAIL`) |
| `MAIL_MODE` | `console` (par défaut) : les e-mails ne sont pas envoyés mais affichés dans la console du serveur, lien compris. `smtp` : envoyés à Mailpit (ou à un vrai serveur SMTP) |
| `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM` | Serveur d'envoi en mode `smtp` (Mailpit : `localhost`, `1025`). Pour un vrai fournisseur : `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS=true` |
| `APP_URL` | Adresse du jeu dans les liens des e-mails (par défaut `http://127.0.0.1:8000`) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Identifiants de la base PostgreSQL créée par `docker compose` |
| `DATABASE_URL` | Adresse de la base : `postgresql+psycopg://utilisateur:mot_de_passe@localhost:5432/nom_de_la_base` (mêmes valeurs que ci-dessus). Vide : fichier SQLite `data/lantern_hollow.db` |
| `TEST_DATABASE_URL` | Facultatif : lancer les tests sur PostgreSQL (voir Tests) |

`JWT_SECRET` doit être une **longue chaîne aléatoire** (au moins 32 caractères), jamais un mot ou une phrase : qui la connaît peut se faire passer pour n'importe quel compte, admin compris. Pour en obtenir une, lancer une fois dans le terminal l'une de ces commandes et coller le résultat dans `.env` :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
openssl rand -hex 32
```

Le fichier `.env` ne doit jamais être commité.

## Adresses du serveur

Une fois lancé (`python main.py`), le serveur répond sur `http://127.0.0.1:8000` :

| Adresse | Rôle |
|---|---|
| `GET /` | Interface web : accueil et jeu (fichiers de `static/`) |
| `GET /dashboard.html` | Tableau de bord du joueur connecté |
| `GET /health` | Vérifie que le serveur tourne |
| `GET /docs` | Documentation automatique de l'API (FastAPI) |
| `ws://<serveur>/ws/{pseudo}` | WebSocket du joueur : lance ou reprend sa partie, reçoit et valide ses actions |
| `/api/auth/*`, `/api/account/*` | Inscription, connexion, déconnexion, mot de passe oublié, profil |
| `GET /reset-password.html` | Choix d'un nouveau mot de passe (lien reçu par e-mail) |
| `GET /verify-email.html` | Confirmation de l'adresse e-mail (lien reçu par e-mail) |
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
- la liste des comptes, avec pour chacun :
  - un bouton pour réinitialiser le mot de passe d'un joueur qui l'a oublié (mot de passe temporaire affiché une seule fois, à lui transmettre) ;
  - un bouton pour supprimer le compte à la demande du joueur, après confirmation (même suppression que depuis le tableau de bord). Le compte admin ne peut être ni réinitialisé ni supprimé ;
  - un bouton « Historique » : les parties du joueur, dont on peut afficher le **détail complet** (chat, votes, nuits, mémoire des IA) dans les sections du panel, et le **registre des modifications** de son compte (type et date : compte créé, adresse confirmée ou remplacée, pseudo ou mot de passe modifiés…).

Le détail d'une partie est enregistré à sa fin, pour les comptes seulement, et gardé **6 mois** ; le registre des modifications, **un an**. Tous deux sont supprimés avec le compte, et effacés automatiquement à échéance par la tâche de nettoyage quotidienne. Le joueur les retrouve dans l'export de ses données.

## Scripts

À lancer depuis la racine du projet. Les trois premiers appellent les vrais modèles (clés d'API nécessaires, plus lents) :

```bash
python scripts/play_with_human.py   # tu joues contre les 5 IA dans le terminal
python scripts/play_ai_game.py      # les IA jouent seules (le 6e joueur s'abstient et ne parle pas)
python scripts/check_nights.py      # les IA jouent seulement des nuits : contrôle de leurs cibles
python scripts/simulate_game.py     # partie simulée, sans LLM : affiche chaque message reçu par le front
python scripts/check_full_game.py   # partie simulée, sans LLM, avec des centaines de vérifications
python scripts/demo_players.py      # 10 joueurs de démonstration (comparaison du tableau de bord) ; --remove pour les retirer
```

Les joueurs de démonstration ont une adresse en `@demo.lantern-hollow.invalid` (domaine réservé : aucun e-mail ne peut y partir) et un mot de passe aléatoire jamais affiché. `--remove` les efface entièrement, parties comprises, pour ne rien laisser dans les statistiques.

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

Les tests n'appellent jamais de vrai LLM : ils utilisent de faux agents, ou le mode simulation. Ils n'utilisent jamais la base du jeu : chaque test a sa base SQLite en mémoire (`tests/conftest.py`), et le compte admin du `.env` est ignoré. Les migrations sont testées : elles créent exactement les tables de `models.py` et peuvent être annulées puis rejouées.

Pour lancer les tests du backend sur PostgreSQL, sur une base dédiée créée au premier `docker compose up` et vidée avant chaque test :

```bash
TEST_DATABASE_URL=postgresql+psycopg://lantern:lantern@localhost:5432/lantern_hollow_test python -m pytest tests/ -q --ignore=tests/frontend
``` `tests/integration/test_full_game.py` joue des parties complètes avec `scripts/check_full_game.py`. À lancer depuis la racine du projet.

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
- Comptes (invité ou compte, connexion par cookie avec le pseudo ou l'e-mail), adresse confirmée par e-mail, mot de passe oublié par e-mail, tableau de bord, statistiques, historique des parties, succès ; compte admin, réinitialisation des mots de passe et suppression des comptes
- Page 404
- Base PostgreSQL avec Docker Compose, migrations Alembic (SQLite toujours possible sans Docker)

**À faire :**
- Résumer la mémoire des agents au fil des jours : le contexte grandit à chaque événement (voir les limites connues dans `docs/ai_architecture.md`)
- Mise en production : Tailwind est chargé depuis son CDN, à compiler pour la production ; le cookie de connexion est à passer en `Secure` derrière HTTPS (`backend/server/auth.py`)

## Axes d'amélioration

- **Docker pour le serveur** : aujourd'hui seule la base tourne dans Docker, le serveur se lance avec `python main.py`. Une image du serveur, ajoutée au `docker-compose.yml`, permettrait de tout lancer en une commande.
- **Une partie par joueur** : aujourd'hui une seule partie à la fois sur le serveur (une session globale), ce qui suffit en local. Il faudrait une session par joueur, et des messages publics limités à leur partie.
- **Journaux du serveur** : aujourd'hui affichés dans la console seulement. S'ils sont un jour écrits dans des fichiers, limiter leur durée de conservation : ils contiennent des pseudos et des heures.

## Documentation

- [`docs/ai_architecture.md`](docs/ai_architecture.md) : fonctionnement des agents IA (`backend/ai/`) et du tour de jeu
- [`docs/model_choices.md`](docs/model_choices.md) : choix des modèles LLM et leurs résultats aux tests
- [`docs/protocol.md`](docs/protocol.md) : messages échangés entre le front et le serveur (WebSocket)
