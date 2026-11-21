# Protocole WebSocket entre le front et le serveur

Connexion : `ws://<serveur>/ws/<pseudo>`. Un seul joueur humain et une seule partie à la fois.

- Le contrat est défini par des modèles Pydantic dans `backend/server/schemas.py` : **INPUTS** pour les actions du front, **OUTPUTS** pour les messages du serveur. Un champ inconnu ou manquant est une erreur, dans les deux sens.
- **Les joueurs sont toujours désignés par leur identifiant** : `p1` … `p5` pour les agents, le pseudo pour le joueur humain. Le front affiche les noms à partir de la liste des joueurs reçue dans `game_state` (`getPlayerName`).
- Les textes construits à partir de données (morts de la nuit, résultats des votes, titre de fin de partie) sont écrits par le front. Les consignes, annonces et erreurs arrivent déjà rédigées (`text`, `data`).

## Organisation côté serveur

| Fichier | Rôle |
|---|---|
| `backend/server/session.py` | `GameSession` : la partie en cours (tâches, port du moteur, état, demande en attente, chat, salons, historiques). `current_session()` |
| `backend/server/protocol.py` | Traduction des demandes du moteur en messages, envoi, reprise après reconnexion |
| `backend/server/websockets.py` | Endpoint `/ws/{pseudo}` et un traitement par action du front |
| `backend/server/game_runner.py` | Boucle de partie, lancement, refus, abandon |

## Connexion

1. Pseudo refusé (vide, réservé, nom d'un agent) ou partie en cours d'un autre joueur : la connexion est acceptée puis fermée avec le code **4001**, le motif dans `reason`.
2. Sinon : `connected`, puis lancement d'une nouvelle partie ou reprise de la partie en cours.
3. Reprise (rechargement, coupure) : `role_assigned` (avec `allies` si déjà révélés), `game_state`, les salons privés (`private_channel_opened` avec `focus: false`), tout le chat, `history`, puis la demande en attente du moteur, renvoyée telle quelle.

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
| `role_assigned` | `role_name`, `description`, `allies` | Rôle du joueur (à chaque connexion) |
| `game_state` | `state` : `day`, `phase` (`nuit` / `discussion` / `vote`), `aliveCount`, `players` [`id`, `name`, `alive`, `has_vote`] | Avant chaque demande ; source des noms affichés |
| `action_request` | `kind` (`nuit` / `vote` / `discussion`), `candidates` (ids), `max_targets`, `min_targets`, `role` (nom anglais, nuit) | Encadré d'action |
| `input_request` | `kind` (`public_message` / `private_message`), `channel_id`, `text`, `left` | Bandeau « c'est à vous d'écrire » |
| `agent_whisper_request` | `agent_id` | Un agent propose un entretien (modale) |
| `chat` | `channel_id`, `sender` (id, ou `"Grimoire"` pour les annonces), `content` | Message de chat |
| `private_channel_opened` | `channel_id`, `members` (ids), `text`, `focus` | Ouverture (ou réouverture) d'un salon privé |
| `night_info` | `turn`, `info`, `allies` | Information de nuit ; `allies` [`id`, `role`] pour le camp du mal, la première nuit |
| `night_result` | `turn`, `dead_player` (id ou `null`) | Réveil du village |
| `night_action_ack` | `text` | Choix de nuit bien reçu |
| `vote_result` | `turn`, `executed` (id ou `null`), `votes` [`voter`, `target`, `ghost`] | Résultat du vote ; `ghost` : vote fantôme |
| `history` | `nights` [`turn`, `type` (`role_info` / `result`), `info`, `dead_player`], `votes` [`turn`, `voter`, `target`, `executed`] | Onglets Nuits et Votes, à la reconnexion |
| `announcement` | `text` | Annonce courte (bandeau central) |
| `error` | `data` | Action refusée ou invalide |
| `game_over` | `winner` (`good` / `evil`), `details` | Fin de partie |
| `game_abandoned` | — | Abandon confirmé |
| `game_interrupted` | `text` | La partie a planté : le front propose d'en relancer une |
