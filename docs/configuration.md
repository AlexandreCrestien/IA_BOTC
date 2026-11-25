# Configuration et outils

Installation et lancement : [README](../README.md). Fonctionnalités : [features.md](features.md).

## Variables d'environnement

`.env.example`, copié en `.env`, est déjà rempli pour un lancement local, sauf les clés d'API.

| Variable | Rôle |
|---|---|
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY` | Clés d'API des LLM (au moins une). Où les obtenir : README |
| `JWT_SECRET` | Clé qui signe les jetons de connexion. Celle du `.env.example` est une valeur de démonstration, publique : pour un usage réel, en générer une avec `openssl rand -hex 32`. Absente : clé temporaire, les joueurs sont déconnectés à chaque redémarrage |
| `ADMIN_PSEUDO`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | Compte admin, créé au démarrage du serveur s'il n'existe pas (un compte déjà créé garde son mot de passe : changer `ADMIN_PASSWORD` ensuite n'a pas d'effet). Absents : pas de panel admin |
| `CONTACT_EMAIL` | Adresse à contacter, indiquée dans les e-mails de sécurité (à défaut : `ADMIN_EMAIL`) |
| `MAIL_MODE` | `smtp` : e-mails envoyés à Mailpit. `console` : affichés dans la console du serveur |
| `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM` | Serveur d'envoi en mode `smtp` (Mailpit : `localhost`, `1025`). Pour un vrai fournisseur : `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS=true` |
| `APP_URL` | Adresse du jeu dans les liens des e-mails |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Base PostgreSQL créée par `docker compose` |
| `DATABASE_URL` | Adresse de la base. Vide : fichier SQLite `data/lantern_hollow.db` |
| `TEST_DATABASE_URL` | Facultatif : tests sur PostgreSQL (voir plus bas) |
| `SIMULATE_LLM` | `1` : aucun appel aux modèles, réponses tirées au hasard parmi les choix légaux (à passer en ligne de commande) |

Le fichier `.env` n'est jamais commité.

## Services Docker

`docker compose up -d` lance, accessibles depuis cet ordinateur seulement :
- **PostgreSQL** (`127.0.0.1:5432`), avec une base dédiée aux tests (`docker/postgres-init.sql`) ;
- **Mailpit**, faux serveur d'e-mails : il capture les e-mails du jeu sans rien envoyer et les affiche sur http://localhost:8025.

Docker redémarre ces services tout seul (même après un redémarrage de l'ordinateur) tant qu'ils n'ont pas été arrêtés. `docker compose down` les arrête en gardant les données (volume Docker) ; `docker compose down -v` efface les données. Si la base ne répond pas, `uv run main.py` s'arrête avec un message qui rappelle de lancer `docker compose up -d`.

## Sans Docker

Laisser `DATABASE_URL` vide et passer `MAIL_MODE=console` : le jeu utilise un fichier SQLite (`data/lantern_hollow.db`) et affiche les e-mails (et leurs liens) dans la console du serveur.

## Base de données et migrations

Le serveur applique les migrations Alembic au démarrage (`backend/db/migrations/versions/`). Après un changement de `backend/db/models.py` :

```bash
uv run alembic revision --autogenerate -m "description du changement"   # puis relire la migration générée
uv run alembic upgrade head                                            # l'appliquer sans redémarrer
uv run alembic current                                                 # version de la base
```

## Dépendances

Déclarées dans `pyproject.toml`, versions exactes dans `uv.lock`. `requirements.txt` est une copie pour pip, générée depuis `uv.lock`. Pour ajouter une dépendance :

```bash
uv add <paquet>            # ou : uv add --dev <paquet> pour un outil de test
uv export --format requirements-txt --no-hashes --no-emit-project --all-groups -o requirements.txt
```

## Scripts

À lancer depuis la racine du projet. Les trois premiers appellent les vrais modèles (clés d'API nécessaires) :

```bash
uv run scripts/play_with_human.py   # jouer contre les 5 IA dans le terminal
uv run scripts/play_ai_game.py      # les IA jouent seules
uv run scripts/check_nights.py      # les IA jouent seulement des nuits : contrôle de leurs cibles
uv run scripts/simulate_game.py     # partie simulée sans LLM : affiche chaque message reçu par le front
uv run scripts/check_full_game.py   # partie simulée sans LLM, avec des centaines de vérifications
uv run scripts/demo_players.py      # 10 joueurs de démonstration (comparaison du tableau de bord) ; --remove pour les retirer
```

Les joueurs de démonstration ont une adresse en `@demo.lantern-hollow.invalid` (domaine réservé, aucun e-mail ne peut y partir) et un mot de passe aléatoire ; `--remove` les efface entièrement, parties comprises.

## Tests

- Aucun test n'appelle de vrai LLM (faux agents ou mode simulation) ni n'utilise la base du jeu : chaque test a sa base SQLite en mémoire, et le compte admin du `.env` est ignoré.
- Les migrations sont testées : elles créent exactement les tables de `models.py` et peuvent être annulées puis rejouées.
- Les tests du frontend (`tests/frontend/`) pilotent un vrai navigateur avec Playwright, sans serveur ni connexion internet : le serveur est simulé.
- `tests/integration/test_full_game.py` joue des parties complètes avec `scripts/check_full_game.py`.

Tests du backend sur PostgreSQL (base de test créée au premier `docker compose up`, vidée avant chaque test) :

```bash
TEST_DATABASE_URL=postgresql+psycopg://lantern:lantern@localhost:5432/lantern_hollow_test uv run pytest -q --ignore=tests/frontend
```

## Adresses du serveur

| Adresse | Rôle |
|---|---|
| `/` | Accueil et jeu |
| `/dashboard.html` | Tableau de bord du joueur connecté |
| `/admin` | Panel admin |
| `/docs` | Documentation automatique de l'API (FastAPI) |
| `/health` | Vérifie que le serveur tourne |

Routes de l'API et messages WebSocket : [architecture.md](architecture.md#échanges-entre-le-front-et-le-serveur).
