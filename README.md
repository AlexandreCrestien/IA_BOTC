# 🏮 Lantern Hollow

Jeu de déduction sociale inspiré de ***Blood on the Clocktower***, variante du loup-garou : **un joueur humain affronte seul cinq personnages pilotés par des IA**, chacun avec un rôle secret et une personnalité.

Les agents discutent, bluffent, s'entretiennent en privé et votent grâce à des LLM, avec une mémoire qui ne contient que ce que leur personnage peut savoir.

Projet de groupe réalisé dans le cadre de notre formation _Développeur en intelligence artificielle_ à Simplon : concevoir des agents IA crédibles dans un jeu multi-agents, et livrer l'application comme pour un client (comptes, base de données, administration, tests, conformité RGPD et AI Act), entièrement démontrable en local.

## Installation et lancement

### Prérequis

- [Git](https://git-scm.com/downloads)
- [Docker](https://docs.docker.com/get-docker/) avec Docker Compose (Docker Desktop sous Windows et macOS) : base PostgreSQL et faux serveur d'e-mails
- [uv](https://docs.astral.sh/uv/) (recommandé), qui installe lui-même la bonne version de Python :
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh                  # Linux, macOS
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"       # Windows
  ```
  ou, sans uv, [Python](https://www.python.org/downloads/) 3.12 ou plus (testé avec 3.14) et pip
- Au moins une clé d'API LLM, gratuite :

  | Variable du `.env` | Où la créer |
  |---|---|
  | `GROQ_API_KEY` | https://console.groq.com/keys |
  | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
  | `OPENROUTER_API_KEY` | https://openrouter.ai/keys |

  Idéalement les trois : le jeu bascule automatiquement d'un modèle à l'autre en cas d'échec. Sans aucune clé, le jeu se lance en mode simulation (voir plus bas).

### Installer et lancer le jeu

Dans les deux cas, le jeu a besoin de Docker pour la base PostgreSQL et Mailpit (faux serveur d'e-mails) : `docker compose up -d` ne se lance qu'une fois, ils redémarrent ensuite tout seuls.

**Avec uv**

```bash
git clone https://github.com/AlexandreCrestien/IA_BOTC.git
cd IA_BOTC
cp .env.example .env          # Windows : copy .env.example .env  — puis y coller ses clés d'API
docker compose up -d          # base PostgreSQL et Mailpit, en arrière-plan
uv run main.py                # serveur du jeu
```

Au premier `uv run`, uv installe automatiquement Python et les dépendances (dans `.venv`) : pas d'autre commande d'installation. Ensuite, seul `uv run main.py` est nécessaire.

**Avec pip**

```bash
git clone https://github.com/AlexandreCrestien/IA_BOTC.git
cd IA_BOTC
cp .env.example .env          # Windows : copy .env.example .env  — puis y coller ses clés d'API
python -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d          # base PostgreSQL et Mailpit, en arrière-plan
python main.py                # serveur du jeu (ou py main.py, ou python3 main.py, si python n'est pas reconnu)
```

Ensuite, seuls `source venv/bin/activate` (si l'environnement n'est pas activé) et `python main.py` sont nécessaires.

Le `.env` est déjà rempli pour un usage local (valeurs de démonstration, à changer pour un usage réel), sauf les clés d'API.

| Adresse | |
|---|---|
| http://127.0.0.1:8000 | Le jeu : en invité (un pseudo suffit) ou avec un compte |
| http://127.0.0.1:8000/admin | Panel admin : `admin` / `lantern-admin` (valeurs du `.env`) |
| http://localhost:8025 | Mailpit : les e-mails envoyés par le jeu (confirmation d'adresse, mot de passe oublié…) |

Sans clé d'API, pour essayer l'interface (les IA répondent au hasard parmi les choix possibles) : `SIMULATE_LLM=1 uv run main.py`, ou `SIMULATE_LLM=1 python main.py`.

Arrêter : `Ctrl+C` pour le serveur, `docker compose down` pour la base et Mailpit (les données sont gardées).

### Lancer les tests

Les tests n'appellent aucun LLM et n'utilisent pas la base du jeu. Ceux du frontend pilotent un vrai navigateur : il faut l'installer une fois.

**Avec uv**

```bash
uv run playwright install chromium          # une seule fois : navigateur des tests du frontend
uv run pytest -q                            # tous les tests (backend et frontend)
uv run pytest -q --ignore=tests/frontend    # backend seul
uv run pytest tests/frontend -q             # frontend seul (--headed pour voir le navigateur)
uv run ruff check .                         # vérification du code
```

**Avec pip**

```bash
source venv/bin/activate                    # si l'environnement n'est pas activé (Windows : venv\Scripts\activate)
python -m playwright install chromium       # une seule fois : navigateur des tests du frontend
python -m pytest -q                         # tous les tests (backend et frontend)
python -m pytest -q --ignore=tests/frontend # backend seul
python -m pytest tests/frontend -q          # frontend seul (--headed pour voir le navigateur)
ruff check .                                # vérification du code
```

## Stack et documentation

- **Python**, **FastAPI** et **Uvicorn** : serveur HTTP et WebSocket
- **Pydantic** : schémas de validation (messages échangés avec le front, réponses des LLM)
- **LiteLLM** : accès aux LLM (Groq, Gemini, OpenRouter) avec bascule automatique entre modèles
- **PostgreSQL** (Docker Compose), **SQLAlchemy**, **Alembic** : base de données et migrations ; SQLite possible sans Docker
- **bcrypt**, **PyJWT** (cookie `HttpOnly`) : comptes et connexion ; e-mails testés avec **Mailpit**
- **HTML, CSS et JavaScript** sans framework, **Tailwind CSS** : interface web
- **pytest**, **Playwright**, **ruff** : tests et vérification du code

Installation possible avec uv ou avec pip.

| Document | Contenu |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Arborescence détaillée du projet, échanges entre le front et le serveur (WebSocket, routes HTTP) |
| [docs/features.md](docs/features.md) | Règles et rôles, comptes, succès, retours des joueurs sur les IA, panel admin, données personnelles (RGPD) |
| [docs/configuration.md](docs/configuration.md) | Variables d'environnement, Docker, base et migrations, dépendances, scripts, tests |
| [docs/ai.md](docs/ai.md) | Agents IA : mémoire, prompts, déroulement d'un tour, choix des modèles, robustesse |

## Architecture

```
IA_BOTC/
├── main.py                Lance le serveur
├── backend/
│   ├── models/            État de la partie : joueurs, rôles, effets, événements
│   ├── rules/             Règles du jeu : rôles, actions de nuit, vote, victoire
│   ├── engine/            Moteur : mise en place et tour de jeu
│   ├── ai/                Agents IA : accès aux LLM, mémoire, conversations
│   ├── server/            Serveur FastAPI : WebSocket, routes, panel admin
│   ├── accounts/          Comptes : pseudo, mots de passe, connexion, e-mails
│   ├── db/                Base de données : tables et migrations
│   └── stats/             Statistiques et succès
├── skills/                Textes des prompts : règles, rôles, personnalités
├── static/                Interface web : jeu, tableau de bord, panel admin
├── scripts/               Parties dans le terminal, simulations, joueurs de démonstration
├── tests/                 Tests, rangés comme le code
├── docs/                  Documentation détaillée
├── docker-compose.yml     PostgreSQL et Mailpit
├── pyproject.toml         Dépendances, configuration de pytest et ruff
├── requirements.txt       Dépendances pour pip
└── .env.example           Configuration locale, à copier en .env
```

Arborescence détaillée, fichier par fichier : [docs/architecture.md](docs/architecture.md).

## TODO

- **Suivi des coûts** : financiers, tokens consommés et impact écologique des appels aux LLM. Mettredans une nouvelle section du panel admin.
- **Résumé de la mémoire des agents** au fil des jours : leur contexte grandit à chaque événement (voir [docs/ai.md](docs/ai.md)).
- **Opinions des agents sur les autres joueurs** : aujourd'hui, un agent relit tout l'historique à chaque appel sans rien retenir de ses déductions. À la fin de chaque journée, chaque agent pourrait noter en une phrase ses soupçons sur chaque joueur, dans sa mémoire personnelle (5 appels de plus par jour), pour des accusations et des votes plus cohérents.
- **Mesurer la réactivité** : les appels aux LLM passent un par un, avec une pause de 2 secondes après chacun (`CALL_PAUSE_SECONDS`) pour respecter les limites des offres gratuites, soit au moins 30 secondes pour une discussion de 10 messages. Chronométrer une partie, puis ajuster la pause par fournisseur.
- **Tailwind compilé** : il est aujourd'hui chargé depuis son CDN, ce qui n'est pas adapté à la production. (A faire en tout dernier, quand il n'y a plus aucune modification du code.)

## Axes d'amélioration

- **Une partie par joueur** : le serveur ne fait tourner qu'une partie à la fois, ce qui suffit en local.
- **Mise en production** : HTTPS, cookie de connexion `Secure`, vrais secrets (`JWT_SECRET`, compte admin) hors du dépôt, vrai serveur d'e-mails.
- **Plus de contenu** : davantage de rôles et de personnalités, parties à plus de joueurs.
- **Docker pour le serveur** : une image du serveur dans `docker-compose.yml`, pour tout lancer en une commande.
- **Journaux du serveur** : s'ils sont un jour écrits dans des fichiers, limiter leur conservation (ils contiennent des pseudos).

## Contributeurs

- Alexandre Crestien : [@AlexandreCrestien](https://github.com/AlexandreCrestien)
- Edilene da Silva : [@EdileneSilva](https://github.com/EdileneSilva)
- Flora Delacroix : [@flora-delacroix](https://github.com/flora-delacroix)
