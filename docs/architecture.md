# Architecture

Arborescence détaillée du projet, fichier par fichier. Vue d'ensemble : [README](../README.md#architecture).
Fonctionnement des agents IA : [ai.md](ai.md). Échanges entre le front et le serveur : [plus bas](#échanges-entre-le-front-et-le-serveur).

```
IA_BOTC/
├── main.py                        Lance le serveur (vérifie d'abord que la base répond)
├── backend/
│   ├── models/                    État de la partie
│   │   ├── enums.py                   Rôles, phases, camps
│   │   ├── role.py, player.py         Rôle et joueur
│   │   ├── effect.py                  Effets (poison, protection, maître du Valet…)
│   │   ├── game_event.py              Événement de la partie (qui le voit)
│   │   └── game_state.py              État complet d'une partie
│   ├── rules/                     Règles du jeu
│   │   ├── catalogue.py               Les six rôles
│   │   ├── distribution.py            Distribution des rôles, fausse piste du Médium
│   │   ├── first_night.py             Informations de la première nuit
│   │   ├── actions.py                 Actions légales de chaque joueur
│   │   ├── night.py                   Ordre des actions de nuit
│   │   ├── night_effects.py           Protection et meurtre
│   │   ├── poison.py                  Poison de l'Apothicaire
│   │   ├── powers.py                  Pouvoirs d'information (réponse du Médium)
│   │   ├── night_resolution.py        Résolution de la nuit (morts)
│   │   ├── links.py                   Lien d'un joueur vers un autre (maître du Valet)
│   │   ├── valet.py                   Maître du Valet
│   │   ├── vote.py                    Vote et exécution
│   │   ├── victory.py                 Conditions de victoire
│   │   └── fallback.py                Choix légal au hasard (IA qui ne répond pas)
│   ├── engine/                    Moteur de jeu
│   │   ├── setup.py                   Mise en place d'une partie
│   │   ├── turn.py                    Le tour de jeu : nuit, discussion, vote
│   │   ├── steps.py                   Étapes du tour
│   │   ├── human_port.py              Interface entre le moteur et le joueur humain
│   │   └── config.py                  Noms des agents et personnalités
│   ├── ai/                        Agents IA
│   │   ├── llm_client.py              Seul accès aux LLM : profils, bascule entre modèles, réponses JSON
│   │   ├── prompt_loader.py           Assemblage des prompts depuis skills/
│   │   ├── memory_manager.py          Ce que chaque joueur sait
│   │   ├── agent.py                   Un agent : parler, agir la nuit, voter
│   │   ├── choices.py                 Choix de nuit et votes des agents
│   │   ├── conversations.py           Discussions publiques et privées
│   │   └── agent_whispers.py          Entretien simulé entre deux agents
│   ├── server/                    Serveur FastAPI
│   │   ├── app.py                     Application, routes et tâche de nettoyage quotidienne
│   │   ├── websocket_endpoint.py      WebSocket du joueur : connexion, reprise, actions
│   │   ├── protocol.py                Messages envoyés au front
│   │   ├── schemas.py                 Format des messages échangés
│   │   ├── connection_manager.py      Connexions WebSocket ouvertes
│   │   ├── session.py                 La partie en cours
│   │   ├── game_runner.py             Lancement, reprise, abandon d'une partie
│   │   ├── game_records.py            Enregistrement des parties des comptes, succès
│   │   ├── game_view.py               Vue complète d'une partie (panel admin)
│   │   ├── auth.py                    Inscription, connexion, profil, vérification de l'adresse
│   │   ├── account_removal.py         Suppression des comptes, purge des comptes inactifs
│   │   ├── game_routes.py             Partie en cours depuis le tableau de bord
│   │   ├── stats_routes.py            Statistiques, historique, succès, export des données
│   │   ├── reports.py                 Signalements des messages des IA
│   │   ├── ratings.py                 Évaluations des agents en fin de partie
│   │   └── admin.py                   Routes du panel admin
│   ├── accounts/                  Comptes
│   │   ├── service.py                 Opérations sur les comptes et durées de conservation
│   │   ├── pseudo.py                  Règles du pseudo
│   │   ├── passwords.py               Mots de passe (bcrypt)
│   │   ├── tokens.py                  Jetons de connexion (JWT)
│   │   └── emails.py                  Textes des e-mails
│   ├── db/                        Base de données
│   │   ├── models.py                  Tables
│   │   ├── database.py                Connexion et migrations
│   │   ├── games.py                   Requêtes sur les parties
│   │   └── migrations/                Migrations Alembic (versions/0001 à 0006)
│   ├── stats/                     Statistiques et succès
│   │   ├── achievements.py            Les 14 succès et leurs conditions
│   │   └── queries.py                 Statistiques, comparaison, export des données
│   └── mail.py                    Envoi des e-mails (console, Mailpit)
├── skills/                        Textes des prompts
│   ├── general_rules.md               Règles communes à tous les agents
│   ├── roles/                         Un fichier par rôle
│   └── personalities/                 Un fichier par personnalité
├── static/                        Interface web
│   ├── index.html                     Accueil et jeu
│   ├── dashboard.html                 Tableau de bord du joueur
│   ├── admin.html                     Panel admin
│   ├── reset-password.html            Nouveau mot de passe (lien reçu par e-mail)
│   ├── verify-email.html              Confirmation de l'adresse (lien reçu par e-mail)
│   ├── not-found.html                 Page 404
│   ├── css/                           style.css (commun), dashboard.css, admin.css
│   ├── img/                           Image de fond
│   └── js/
│       ├── core.js                        État du jeu et utilitaires
│       ├── connection.js                  WebSocket et messages du serveur
│       ├── game.js, players.js            Plateau et joueurs
│       ├── actions.js                     Panneau d'actions (nuit, discussion, vote)
│       ├── chat.js                        Chat, historiques, signalements
│       ├── modals.js                      Fenêtres (rôle, nuit, fin de partie, évaluation)
│       ├── account.js                     Accueil, connexion et inscription
│       ├── main.js                        Branchement des événements
│       ├── dashboard.js                   Tableau de bord
│       ├── admin.js                       Panel admin
│       ├── section-nav.js                 Raccourcis de l'en-tête (tableau de bord, admin)
│       ├── reset-password.js, verify-email.js   Pages des liens reçus par e-mail
│       └── tailwind.config.js             Thème Tailwind
├── scripts/                       Parties dans le terminal, simulations, joueurs de démonstration
├── tests/                         Tests, rangés comme le code
│   ├── models/, rules/, engine/, ai/      Moteur et agents
│   ├── accounts/, db/, stats/, server/    Comptes, base, statistiques, serveur
│   ├── frontend/                          Interface, dans un vrai navigateur (Playwright)
│   └── integration/                       Parties complètes simulées
├── docs/                          Documentation détaillée
├── docker/postgres-init.sql       Création de la base des tests
├── docker-compose.yml             PostgreSQL et Mailpit
├── alembic.ini                    Configuration des migrations
├── pyproject.toml                 Dépendances, configuration de pytest et ruff
├── uv.lock                        Versions exactes des dépendances (uv)
├── requirements.txt               Mêmes versions, pour pip
├── .python-version                Version de Python utilisée par uv
└── .env.example                   Configuration locale, à copier en .env
```

## Échanges entre le front et le serveur

Deux canaux :
- le **WebSocket** de la partie, `ws://<serveur>/ws/<pseudo>` : un seul joueur humain et une seule partie à la fois ;
- des **routes HTTP** (`/api/…`, `/admin/…`) pour les comptes, le tableau de bord et l'administration.

La connexion à un compte est un **jeton JWT dans un cookie `HttpOnly`** (`lh_session`, `SameSite=Lax`, 7 jours). Le JavaScript ne le lit jamais : le navigateur l'envoie avec chaque requête et à l'ouverture du WebSocket.

- Le contrat est défini par des modèles Pydantic dans `backend/server/schemas.py` : **INPUTS** pour les actions du front, **OUTPUTS** pour les messages du serveur. Un champ inconnu ou manquant est une erreur, dans les deux sens.
- **Les joueurs sont toujours désignés par leur identifiant** : `p1` … `p5` pour les agents, le pseudo pour le joueur humain. Le front affiche les noms à partir de la liste des joueurs reçue dans `game_state` (`getPlayerName`).
- Les textes construits à partir de données (morts de la nuit, résultats des votes, titre de fin de partie) sont écrits par le front. Les consignes, annonces et erreurs arrivent déjà rédigées (`text`, `data`).

## WebSocket

### Connexion

Le serveur identifie le joueur par le cookie de connexion : un compte, ou un invité s'il n'y en a pas.

1. **Refus** : la connexion est acceptée puis fermée avec le code **4001**, le motif dans `reason` (affiché sur l'accueil) :
   - pseudo hors format (1 à 20 caractères parmi lettres, chiffres, `-`, `_` et apostrophes), réservé, ou nom d'un agent ;
   - invité qui prend le pseudo d'un compte ;
   - joueur connecté qui ne joue pas sous le pseudo de son compte ;
   - partie en cours d'un autre joueur ;
   - partie d'un compte que l'on n'a plus le droit de reprendre (session expirée, déconnexion).
2. Sinon : `connected`, puis lancement d'une nouvelle partie ou reprise de la partie en cours.
3. **Invité** : `guest_session` avec un jeton, à présenter à l'inscription ou à la connexion pour rattacher la partie au compte.
4. **Reprise** (rechargement, coupure, onglet fermé puis rouvert) : `role_assigned` (avec `allies` si déjà révélés), `game_state`, les salons privés (`private_channel_opened` avec `focus: false`), tout le chat, `history`, puis la demande en attente du moteur, renvoyée telle quelle.

Fermer l'onglet ne termine pas la partie : elle attend le joueur. Un joueur connecté la reprend avec `/?play` (le front se connecte sous le pseudo de la partie, donné par `GET /api/game/current`).

### Actions du front

Format : `{"action": "<nom>", "payload": {...}}`.

| Action | Payload | Quand |
|---|---|---|
| `send_chat` | `channel_id`, `content` | Message public (`"public"`) ou privé (salon ouvert), seulement quand le moteur l'attend |
| `request_whisper` | `targets` : 1 ou 2 ids | Choix des interlocuteurs du salon privé |
| `discussion_timeout` | — | 10 s sans choix de salon privé : un agent va proposer un entretien |
| `respond_whisper_invitation` | `target_agent_id`, `accepted` | Réponse à la proposition d'un agent (refus : place au vote) |
| `submit_vote` | `target_id` : id, ou `null` pour « Personne » | Vote |
| `submit_night_action` | `targets` : ids | Pouvoir de nuit |
| `skip_turn` | `kind` : `public_message`, `private_message` ou `private_partners` | Passer une étape facultative |
| `abandon_game` | — | Abandon : le front revient à l'accueil |
| `report_message` | `message_id`, `category` (`knowledge`, `rules`, `character`, `inappropriate`, `other`), `comment` (facultatif, 200 caractères ; obligatoire pour `other`, 500 caractères) | Signalement d'un message d'agent IA, joueur connecté seulement (10 par partie, un par message). Réponse : `report_result` |
| `rate_agents` | `ratings` : 1 à 5 éléments `{agent_id, score (1 à 5), comment (facultatif, 300 caractères)}`, un par agent | Évaluation des agents sur l'écran de fin : joueur connecté, partie gagnée ou perdue, une fois par partie. Réponse : `rating_result` |

Une action hors de son moment, ou avec un choix non proposé, reçoit un message `error`.

### Messages du serveur

| `type` | Champs | Usage |
|---|---|---|
| `connected` | — | Accusé de connexion : le front affiche l'écran de jeu |
| `guest_session` | `guest_token` | Partie d'invité : jeton gardé en mémoire par le front (jamais affiché), envoyé avec une inscription ou une connexion |
| `role_assigned` | `role_name`, `description`, `allies` | Rôle du joueur (à chaque connexion) |
| `game_state` | `state` : `day`, `phase` (`nuit` / `discussion` / `vote`), `aliveCount`, `players` [`id`, `name`, `alive`, `has_vote`] | Avant chaque demande ; source des noms affichés |
| `action_request` | `kind` (`nuit` / `vote` / `discussion`), `candidates` (ids), `max_targets`, `min_targets`, `role` (nom anglais, nuit) | Encadré d'action |
| `input_request` | `kind` (`public_message` / `private_message`), `channel_id`, `text`, `left` | Bandeau « c'est à vous d'écrire » |
| `agent_whisper_request` | `agent_id` | Un agent propose un entretien (modale) |
| `chat` | `channel_id`, `sender` (id, ou `"Codex"` pour les annonces), `content`, `message_id` (messages des IA seulement, sinon `null`), `reported` (déjà signalé, pour la reprise) | Message de chat. Le modèle qui a écrit un message d'IA reste sur le serveur |
| `private_channel_opened` | `channel_id`, `members` (ids), `text`, `focus` | Ouverture (ou réouverture) d'un salon privé |
| `night_info` | `turn`, `info`, `allies` | Information de nuit ; `allies` [`id`, `role`] pour le camp du mal, la première nuit |
| `night_result` | `turn`, `dead_player` (id ou `null`) | Réveil du village |
| `night_action_ack` | `text` | Choix de nuit bien reçu |
| `vote_result` | `turn`, `executed` (id ou `null`), `votes` [`voter`, `target`, `ghost`, `unavailable`] | Résultat du vote ; `ghost` : voix d'outre-tombe utilisée ; `unavailable` : l'IA du votant n'a pas répondu (abstention forcée) |
| `history` | `nights` [`turn`, `type` (`role_info` / `result`), `info`, `dead_player`], `votes` [`turn`, `voter`, `target`, `executed`, `unavailable`] | Onglets Nuits et Votes, à la reconnexion |
| `announcement` | `text` | Annonce courte (bandeau central) |
| `error` | `data` | Action refusée ou invalide |
| `game_over` | `winner` (`good` / `evil`), `details`, `achievements` [`code`, `title`, `description`, `message`] | Fin de partie ; succès débloqués par la partie (joueur connecté) |
| `game_abandoned` | — | Abandon confirmé |
| `report_result` | `message_id`, `error` (motif du refus, `null` si le signalement est enregistré) | Réponse à `report_message`, à part des `error` : la demande en cours n'est pas touchée |
| `rating_result` | `error` (motif du refus, `null` si l'évaluation est enregistrée) | Réponse à `rate_agents` |
| `game_interrupted` | `text` | La partie a planté : le front propose d'en relancer une |

## Routes HTTP

Le détail de chaque route (paramètres, réponses) est dans la documentation automatique de FastAPI : **http://127.0.0.1:8000/docs**, serveur lancé.

| Préfixe | Fichier | Rôle |
|---|---|---|
| `/api/auth`, `/api/account` | `auth.py` | Inscription, connexion, déconnexion, confirmation de l'adresse, mot de passe oublié, profil, suppression du compte |
| `/api/game` | `game_routes.py` | Partie en cours, abandon depuis le tableau de bord |
| `/api/me` | `stats_routes.py` | Statistiques, comparaison, historique, succès, export des données |
| `/admin` | `admin.py` | Partie en cours, comptes, historique d'un joueur, signalements, évaluations (compte admin uniquement) |

Réponses en JSON. Une erreur renvoie `{"detail": "<message en français>"}`, affiché tel quel par le front. Sans connexion, une route réservée renvoie **401** ; un compte joueur sur une route admin, **403**. Tant que l'adresse n'est pas confirmée (sauf compte admin), les routes du tableau de bord (`/api/me/stats`, `games`, `achievements`), l'abandon et le changement de pseudo ou de mot de passe renvoient **403** ; restent possibles : `/api/auth/me`, la correction de l'adresse, le renvoi du lien, l'export et la suppression du compte. Le WebSocket refuse une nouvelle partie avec ce compte (seule la partie rattachée à l'inscription peut être reprise).

Une page inconnue demandée par le navigateur reçoit la page 404 du jeu ; `/api/…` et `/admin/…` gardent leur réponse JSON.
