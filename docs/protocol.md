# Protocole entre le front et le serveur

Deux canaux :
- le **WebSocket** de la partie, `ws://<serveur>/ws/<pseudo>`. Un seul joueur humain et une seule partie à la fois ;
- des **routes HTTP** (`/api/…`, `/admin/…`) pour les comptes, le tableau de bord et l'administration, hors de l'écran de jeu.

La connexion à un compte est un **jeton JWT dans un cookie `HttpOnly`** (`lh_session`, `SameSite=Lax`, 7 jours), posé par le serveur à l'inscription ou à la connexion. Le JavaScript ne le lit jamais : le navigateur l'envoie avec chaque requête HTTP et à l'ouverture du WebSocket.

- Le contrat est défini par des modèles Pydantic dans `backend/server/schemas.py` : **INPUTS** pour les actions du front, **OUTPUTS** pour les messages du serveur. Un champ inconnu ou manquant est une erreur, dans les deux sens.
- **Les joueurs sont toujours désignés par leur identifiant** : `p1` … `p5` pour les agents, le pseudo pour le joueur humain. Le front affiche les noms à partir de la liste des joueurs reçue dans `game_state` (`getPlayerName`).
- Les textes construits à partir de données (morts de la nuit, résultats des votes, titre de fin de partie) sont écrits par le front. Les consignes, annonces et erreurs arrivent déjà rédigées (`text`, `data`).

## Organisation côté serveur

| Fichier | Rôle |
|---|---|
| `backend/server/session.py` | `GameSession` : la partie en cours (tâches, port du moteur, état, demande en attente, chat, salons, historiques). `current_session()` |
| `backend/server/protocol.py` | Traduction des demandes du moteur en messages, envoi, reprise après reconnexion |
| `backend/server/websocket_endpoint.py` | Endpoint `/ws/{pseudo}` et un traitement par action du front |
| `backend/server/game_runner.py` | Boucle de partie, lancement, refus, abandon |
| `backend/server/game_records.py` | Enregistrement de la partie pour le compte du joueur, rattachement d'une partie d'invité, succès |
| `backend/server/auth.py` | Routes `/api/auth`, `/api/account` ; dépendances `current_user`, `admin_user` |
| `backend/server/game_routes.py`, `stats_routes.py`, `admin.py` | Routes `/api/game`, `/api/me`, `/admin` |

## Connexion au WebSocket

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

## Actions du front

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

Une action hors de son moment, ou avec un choix non proposé, reçoit un message `error`.

## Messages du serveur

| `type` | Champs | Usage |
|---|---|---|
| `connected` | — | Accusé de connexion : le front affiche l'écran de jeu |
| `guest_session` | `guest_token` | Partie d'invité : jeton gardé en mémoire par le front (jamais affiché), envoyé avec une inscription ou une connexion |
| `role_assigned` | `role_name`, `description`, `allies` | Rôle du joueur (à chaque connexion) |
| `game_state` | `state` : `day`, `phase` (`nuit` / `discussion` / `vote`), `aliveCount`, `players` [`id`, `name`, `alive`, `has_vote`] | Avant chaque demande ; source des noms affichés |
| `action_request` | `kind` (`nuit` / `vote` / `discussion`), `candidates` (ids), `max_targets`, `min_targets`, `role` (nom anglais, nuit) | Encadré d'action |
| `input_request` | `kind` (`public_message` / `private_message`), `channel_id`, `text`, `left` | Bandeau « c'est à vous d'écrire » |
| `agent_whisper_request` | `agent_id` | Un agent propose un entretien (modale) |
| `chat` | `channel_id`, `sender` (id, ou `"Codex"` pour les annonces), `content` | Message de chat |
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
| `game_interrupted` | `text` | La partie a planté : le front propose d'en relancer une |

## Routes HTTP

Réponses en JSON. Une erreur renvoie `{"detail": "<message en français>"}`, affiché tel quel par le front. Sans connexion, une route réservée renvoie **401** ; un compte joueur sur une route admin, **403**. Tant que l'adresse n'est pas confirmée (sauf compte admin), les routes du tableau de bord (`/api/me/stats`, `games`, `achievements`), l'abandon et le changement de pseudo ou de mot de passe renvoient **403** ; restent possibles : `/api/auth/me`, la correction de l'adresse, le renvoi du lien, l'export et la suppression du compte. Le WebSocket refuse une nouvelle partie avec ce compte (seule la partie rattachée à l'inscription peut être reprise).

### Comptes (`backend/server/auth.py`)

| Route | Corps | Réponse |
|---|---|---|
| `POST /api/auth/register` | `pseudo`, `email`, `password`, `guest_token` (facultatif) | Compte créé et connecté (cookie), lien de confirmation envoyé à l'adresse : `id`, `pseudo`, `email`, `email_verified`, `pending_email`, `is_admin`, `game_claimed`, `achievements`. 409 si le pseudo ou l'adresse est déjà pris |
| `POST /api/auth/verify-email` | `token` | Adresse confirmée (lien de `verify-email.html?token=…`, usage unique, 24 heures ; sans besoin d'être connecté). 400 si le lien a déjà servi ou a expiré |
| `POST /api/account/verification-email` | — | Nouveau lien de confirmation (adresse non confirmée, ou nouvelle adresse en attente). 3 au plus en 15 minutes ; 400 si rien n'est à confirmer |
| `POST /api/auth/login` | `login` (pseudo ou adresse e-mail), `password`, `guest_token` (facultatif) | Comme l'inscription. 401 si l'identifiant ou le mot de passe est faux (même message dans les deux cas) ; 429 après 5 échecs en 5 minutes pour un même compte |
| `POST /api/auth/forgot-password` | `email` | Toujours la même réponse (`message`), que l'adresse ait un compte ou non. Si oui : e-mail avec un lien `reset-password.html?token=…` (usage unique, 30 minutes). 3 demandes au plus par adresse en 15 minutes |
| `POST /api/auth/reset-password` | `token`, `new_password` | Nouveau mot de passe ; tous les appareils sont déconnectés. 400 si le lien a déjà servi ou a expiré |
| `POST /api/auth/logout` | — | 204, cookie effacé |
| `GET /api/auth/me` | — | Compte connecté : `id`, `pseudo`, `email`, `email_verified`, `pending_email` (nouvelle adresse à confirmer), `is_admin` |
| `PATCH /api/account/email` | `current_password`, `email` | Lien de confirmation envoyé à la nouvelle adresse. Adresse actuelle confirmée : elle reste en place jusqu'à la confirmation (`pending_email`) ; sinon (faute de frappe à l'inscription), elle est remplacée. 409 si l'adresse est déjà prise |
| `PATCH /api/account/pseudo` | `current_password`, `pseudo` | 409 pendant une partie en cours du compte |
| `PATCH /api/account/password` | `current_password`, `new_password` | Les autres appareils sont déconnectés ; celui-ci reçoit un nouveau cookie |
| `DELETE /api/account` | `current_password` | 204 : compte et succès supprimés, parties gardées anonymement, partie en cours arrêtée, cookie effacé. 403 si le mot de passe est faux, 400 pour le compte admin |

`guest_token` : la partie de l'invité (en cours, ou gagnée ou perdue et encore affichée) est rattachée au compte (`game_claimed`). Si elle était terminée, `achievements` contient les succès qu'elle débloque.

### Partie et tableau de bord

| Route | Réponse |
|---|---|
| `GET /api/game/current` | `running`, `pseudo` (nom du joueur dans la partie), `turn`, `yours` (partie de ce compte, ou partie d'invité pour un visiteur non connecté) |
| `POST /api/game/abandon` | Abandon de sa partie (défaite). Si l'écran de jeu est ouvert, il reçoit `game_abandoned` |
| `GET /api/me/stats` | `played`, `wins`, `win_rate`, `good` et `evil` (`played`, `wins`, `win_rate`), `average_turns` |
| `GET /api/me/games` | Parties terminées ou interrompues, de la plus récente à la plus ancienne : `date`, `role`, `role_name`, `alignment`, `status` (`won` / `lost` / `abandoned` / `interrupted`), `counted`, `turns` |
| `GET /api/me/export` | Fichier JSON à télécharger (`Content-Disposition: attachment`) : `export`, `account`, `account_history` (registre des modifications), `games` (partie en cours comprise, avec `detail` tant qu'il est gardé), `achievements` (débloqués), `statistics`. Jamais l'empreinte du mot de passe |
| `GET /api/me/achievements` | Les 14 succès : `code`, `title`, `description`, `message`, `hidden`, `unlocked`, `unlocked_at`. Caché et non débloqué : `title` « ??? », sans message |

### Administration (`backend/server/admin.py`, compte admin uniquement)

| Route | Réponse |
|---|---|
| `GET /admin/debug/all-states` | État complet de la partie présente sur le serveur (rien n'est caché) |
| `GET /admin/users` | Comptes : `id`, `pseudo`, `email`, `is_admin`, `created_at` |
| `POST /admin/users/{id}/reset-password` | `pseudo`, `temporary_password` (affiché une seule fois). Refusé pour le compte admin |
| `GET /admin/users/{id}/games` | Parties du joueur, de la plus récente à la plus ancienne : `id`, `date`, `role_name`, `alignment`, `status`, `turns`, `has_detail` (détail encore gardé) |
| `GET /admin/games/{id}` | `game` (résumé et `pseudo`) et `detail` (même forme que `/admin/debug/all-states`). 404 si le détail a été effacé (plus de 6 mois) |
| `GET /admin/users/{id}/events` | Registre des modifications du compte, du plus récent au plus ancien : `kind`, `label`, `date` |
| `DELETE /admin/users/{id}` | 204 : même suppression que `DELETE /api/account` ; sa partie en cours est arrêtée (l'écran de jeu reçoit `game_abandoned`). Refusé pour le compte admin |

### Adresse inconnue

Une page demandée par le navigateur reçoit la page 404 du jeu (`static/not-found.html`) ; `/api/…` et `/admin/…` gardent leur réponse JSON ; un fichier manquant (script, style, image) reçoit une 404 simple.
