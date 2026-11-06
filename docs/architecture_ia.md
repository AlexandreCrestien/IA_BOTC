# Architecture IA : `llm_client`, `memory_manager`, `agent_factory` et `conversations`

*Partie « AI & Memory Architect ». Ce document décrit les quatre modules, ce que chacun fait, et comment ils s'enchaînent.*

## Vue d'ensemble

Chaque module a une seule responsabilité :

| Module | Responsabilité | Ne fait jamais |
|---|---|---|
| `backend/llm_client.py` | **Comment** parler aux modèles (choix du modèle, fallback, JSON) | Rien de spécifique au jeu |
| `backend/memory_manager.py` | **Ce que** chaque joueur sait (qui a vu quoi) | Appeler un LLM, décider des règles |
| `backend/agent_factory.py` | **Assembler** un personnage IA : prompt + mémoire + LLM | Enregistrer dans la mémoire, décider ce qui est légal |
| `backend/conversations.py` | **Qui parle et quand** pendant les conversations publiques et privées | Gérer la boucle de jeu, le timer ou l'interface |

Les dépendances vont dans un seul sens :

```
conversations ──► agent_factory ──► memory_manager ──► models (GameEvent, EventType, Phase)
      │                 │
      │                 ├────────► prompt_loader ──► skills/*.md
      │                 │
      │                 └────────► llm_client ──► LiteLLM (Groq, Gemini, OpenRouter)
      │
      └──────────────► memory_manager
```

`memory_manager` et `llm_client` ne se connaissent pas. Seul `agent_factory` les relie.

Ces modules sont appelés par le moteur : `game_engine` (mise en place), `ai_turns` et `human_turns` (déroulement d'un tour), voir section 5.

---

## 1. `llm_client.py` : la seule porte vers les LLM

**Règle :** aucun autre fichier du projet n'importe `litellm`. Tout passe par ce module.

### Profils et fallback

Le code ne demande jamais un modèle précis, mais un **profil** :

| Profil | Usage | Timeout | `max_tokens` |
|---|---|---|---|
| `"fast"` | Messages du salon public, conversations privées | 10 s | 1000 |
| `"capable"` | Actions de nuit, votes | 25 s | 2000 |

Chaque profil est une **liste ordonnée de modèles** (`FAST_MODELS`, `CAPABLE_MODELS`). Le choix et l'ordre sont justifiés dans [`choix_des_modeles.md`](choix_des_modeles.md).

Le `Router` de LiteLLM, créé **une seule fois** au chargement du module :
- donne à chaque modèle un surnom unique (`fast-1`, `fast-2`… `capable-1`…) ;
- en cas d'échec, passe au modèle suivant de la liste (`fallbacks`) ;
- ne réessaie pas le même modèle (`num_retries=0`) : on passe directement au suivant ;
- met de côté pendant 60 s un modèle qui a échoué 2 fois (`allowed_fails`, `cooldown_time`).

### Fonctions publiques

| Fonction | Renvoie | Détails |
|---|---|---|
| `await ask_llm(profile, messages)` | `str` | Texte de la réponse. Lève une erreur si la réponse est vide. |
| `await ask_llm_json(profile, messages, schema, context=None)` | objet Pydantic | Demande du JSON, retire les balises ` ```json `, valide avec `schema`. En cas de JSON invalide, de refus ou de choix illégal, redemande en expliquant l'erreur (2 essais au total, `JSON_ATTEMPTS`). `context` est transmis aux validateurs du schéma. |

**Si tous les modèles échouent**, l'exception remonte. C'est à l'appelant de prendre une décision par défaut : par exemple `random_legal_choice` (dans `backend/rules`) pour une action de nuit. Attraper `Exception` de façon générale : le type exact varie selon la dernière erreur de la chaîne.

### Logs

Chaque appel écrit une ligne `INFO` : profil, modèle qui a vraiment répondu, durée, tokens. Pour les voir :

```python
import logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("backend.llm_client").setLevel(logging.INFO)
logging.getLogger("backend.conversations").setLevel(logging.INFO)  # tours passés, agents en échec
```

---

## 2. `memory_manager.py` : qui sait quoi

### Principe

Toute information de la partie est un **événement**, et chaque événement indique **qui peut le voir** (`visible_to`). La mémoire est la liste chronologique des événements ; ce qu'un joueur sait, c'est cette liste **filtrée** pour lui.

### L'événement : `GameEvent` (défini dans `backend/models`)

`memory_manager` utilise le modèle commun `GameEvent` (alias `Event`). Il est **figé** : on ne peut pas le modifier après sa création.

| Champ | Type | Sens |
|---|---|---|
| `turn` | `int` | Numéro du tour (nuit N, puis jour N) |
| `phase` | `Phase` | `NUIT`, `DISCUSSION` ou `VOTE` |
| `type` | `EventType` | `announcement`, `death`, `public_message`, `private_meeting`, `private_summary`, `nomination`, `vote`, `night_action`, `night_info`, `role_info` |
| `author_id` | `str \| None` | Id d'un joueur ; `None` = le Maître du Jeu |
| `content` | `str` | Le texte de l'événement |
| `visible_to` | `frozenset[str] \| None` | `None` = tout le monde ; sinon, les ids qui peuvent le voir |

Pour écrire au nom du Maître du Jeu, on passe l'auteur `game_master` : la mémoire le convertit en `author_id=None`.

### Qui voit quoi

| Événement | Visible par | Méthode |
|---|---|---|
| Annonce, mort, message public, vote, « Conversation privée entre A, B » | Tous | `add_public` |
| Messages d'une conversation privée, alliance entre démons | Les participants | `add_private` |
| Action de nuit, information de nuit, rôle | Un seul joueur | `add_personal` |
| Fausse piste de la Voyante, joueur empoisonné, vrais rôles | **Personne** : c'est l'état du jeu (`GameState`), pas la mémoire | — |

La mémoire **ne décide pas** si une information est vraie ou fausse (empoisonnement, fausse piste) : elle enregistre ce que l'orchestrateur lui donne.

### Méthodes de `MemoryManager(player_ids, names=None)`

`names` est un dictionnaire `{id: nom affiché}`. Avec lui, l'historique montre les **noms** (ceux que les agents connaissent) ; sans lui, il montre les ids. Les ids restent la seule façon de désigner un joueur dans les méthodes.

L'horloge n'est **pas** calculée par la mémoire : elle vient de `GameState`. Le moteur appelle `set_moment(turn, phase)` à chaque changement de phase, et chaque événement est daté avec ce moment.

| Méthode | Rôle |
|---|---|
| `set_moment(turn, phase)` | Fixe le moment courant (tour et phase), recopié depuis `GameState`. La partie commence à la nuit 1. |
| `add_event(type, author, content, visible_to)` | Fonction générique. Si l'auteur est un joueur, il est ajouté automatiquement aux lecteurs. |
| `add_public` / `add_private` / `add_personal` | Raccourcis qui fixent `visible_to`. |
| `events_for(player)` | **Seule façon de lire la mémoire** : les événements visibles par ce joueur, dans l'ordre. Renvoie une nouvelle liste. |
| `private_partners(player)` | Les joueurs avec qui ce joueur a déjà eu une conversation privée (lu à partir des événements `private_summary`). |
| `context_for(player)` | Les événements visibles, sous forme de texte en français pour le prompt. Auteurs et participants y sont écrits avec leur nom. |
| `name_of(player)` | Nom affiché d'un joueur (son id si aucun nom n'a été donné). |

### Protections (lèvent `ValueError`)

- ids de joueurs en double, ou joueur nommé `game_master` ;
- `names` qui ne contient pas exactement les ids des joueurs ;
- auteur inconnu ;
- lecteur inconnu, ou liste de lecteurs vide ;
- lecture par un joueur inconnu.

### Exemple de `context_for("p1")`

Avec `MemoryManager(["p1", "p2", "p3", "p5"], names={"p1": "Ana", "p2": "Bruno", "p3": "Carla", "p5": "Eva"})` :

```
[Nuit 1] (personnel) Maître du Jeu : Tu es le Moine.
[Nuit 1] (personnel) Toi : Je protège Bruno.
[Jour 1] (public) Maître du Jeu : Le jour 1 se lève. Personne n'est mort cette nuit.
[Jour 1] (public) Carla : Bonjour à tous !
[Jour 1] (public) Maître du Jeu : Conversation privée entre Eva, Ana.
[Jour 1] (privé avec Eva) Toi : Je soupçonne Carla.
```

Les phases `DISCUSSION` et `VOTE` s'affichent toutes les deux « Jour ». Le canal (`public` / `personnel` / `privé avec …`) aide l'agent à ne pas répéter en public ce qu'il a appris en privé.

---

## 3. `agent_factory.py` : les personnages IA

### Le prompt d'un agent

1. **Base assemblée par `PromptLoader`** (`backend/prompt_loader.py`) : contexte du jeu, skill de rôle (`skills/roles/<role>.md`), skill de personnalité (`skills/personalities/<personnalité>.md`) et règles générales (`skills/general_rules.md`). Ces règles comprennent la concision (2 phrases maximum), « pas de mort la première nuit », « ne rien inventer », le secret du privé et le secret de l'allié démon.
2. **La liste des joueurs présents** (par leur nom), ajoutée à chaque appel.

À chaque appel, on ajoute un message avec **ce que l'agent sait** (`memory.context_for`) et **l'instruction du moment**.

### `Agent(player, personality, memory, system_prompt, personality_key=None)`

| Attribut | Sens |
|---|---|
| `player` | Le `Player` (de `backend/models`) au moment de la création |
| `player_id`, `name`, `role_name` | Raccourcis vers `player.id`, `player.name`, `player.role.name_FR` |
| `personality` | Nom affiché de la personnalité (ex. `"Provocateur"`) |
| `personality_key` | Identifiant stable = nom du fichier skill (ex. `"agitator"`). C'est lui qu'on utilise pour les règles (ordre de parole). Par défaut, égal à `personality`. |

| Méthode | Profil | Renvoie |
|---|---|---|
| `await speak_public(optional=False)` | fast | Texte du message. Avec `optional=True`, l'instruction dit que passer est un choix normal et qu'il ne faut parler que pour apporter du nouveau ; si l'agent répond `PASSE` (même avec ponctuation, guillemets ou gras), la méthode renvoie `None`. |
| `await speak_private(partners)` | fast | Réponse dans une conversation privée. `partners` = ids ; le prompt montre leurs noms. |
| `await night_action(options, number_of_targets=1)` | capable | Liste des cibles (2 pour la Voyante) |
| `await vote(options)` | capable | Vote de fin de jour : le nom du joueur qui doit mourir, ou `None` pour « Personne » |
| `await nominate(options)` | capable | Le nom du joueur que l'agent désigne pour l'exécution, ou `None` |
| `await vote_on(nominee)` | capable | `True` (pour l'exécution du joueur désigné) ou `False` (contre) |

- `options` = les **choix légaux**, fournis par le moteur de règles (`legal_actions(state, id).targets` pour la nuit). Un choix hors des options est refusé par la validation et redemandé au modèle.
- La `raison` donnée par le modèle va **seulement dans les logs**, jamais dans la mémoire.
- Les méthodes **renvoient** un résultat : elles n'écrivent pas dans la mémoire.

### Création : `AgentFactory` et `create_all_agents`

- `AgentFactory(prompt_loader=None).create_agent(agent_id, agent_name, role_data, personality_data, memory)` crée un agent. `role_data` est un dictionnaire de `Role` ; `personality_data` contient `personality_name_EN` (nom du fichier skill) et, en option, `personality_name_FR` (nom affiché).
- `create_all_agents(assignments, memory, human_id, prompt_loader=None)` crée un agent par joueur IA à partir de `{id: (nom, role_data, personality_data)}`. L'humain n'a pas d'agent.

---

## 4. `conversations.py` : les phases de conversation

### Ordre et obligation de parole

Le tableau `personalities` donne, pour chaque `personality_key`, l'ordre de parole et si l'agent est obligé de parler :

| Personnalité | Ordre | Obligé de parler |
|---|---|---|
| `agitator` | 1 | oui |
| `paranoid` | 2 | oui |
| `clown` | 3 | oui |
| `strategist` | 4 | non |
| `observer` | 5 | non |

Une personnalité absente du tableau parle en dernier, sans obligation.

### Conversation publique : `await public_conversation(agents, memory, max_messages=10)`

- `agents` : les agents IA seulement (l'humain ne participe pas à cette phase).
- Les agents parlent à tour de rôle dans l'ordre du tableau ; ceux qui ne sont pas obligés peuvent passer.
- Chaque message est enregistré **tout de suite** dans la mémoire (`public_message`), pour que l'agent suivant le voie.
- Arrêt à `max_messages` messages au total, ou quand un tour entier se passe sans aucun message (évite une boucle infinie).
- Si le LLM d'un agent échoue, cet agent ne parle pas et la discussion continue.
- Renvoie la liste `(id_joueur, texte)`, dans l'ordre, pour l'affichage.

### Conversation privée

| Fonction | Rôle |
|---|---|
| `choose_agent_for_human(agents, human_id, memory)` | Quand l'humain n'a choisi personne : choisit l'agent qui vient lui parler. Priorité à ceux qui n'ont jamais discuté avec lui (`private_partners`), puis la personnalité la plus bavarde. |
| `await start_private_conversation(human_id, partners, memory, agent_speaks_first=False)` | Ouvre la conversation avec 1 ou 2 agents. Annonce en public « Conversation privée entre … », sans le contenu. Avec `agent_speaks_first=True`, l'agent ouvre la conversation. |
| `await private_message(human_id, text, partners, memory)` | L'humain envoie un message ; chaque agent répond à son tour. Appelé à chaque message de l'humain. |

- Les messages privés (de l'humain et des agents) sont enregistrés en `private_summary`, visibles seulement des participants.
- Chaque réponse est enregistrée tout de suite : dans une conversation à trois, le second agent voit la réponse du premier.
- 0 ou plus de 2 agents, ou l'humain dans `partners` : `ValueError`.
- Le choix de l'humain arrive en paramètre : ces fonctions ne posent jamais de question elles-mêmes.

### Conversation simulée entre agents : `await simulate_agents_conversation(agents, memory)`

Pendant la conversation privée de l'humain, les autres agents (2 ou plus) discutent entre eux. Pour limiter les appels, tout l'échange est **simulé en un seul appel LLM** (profil capable), comme le prévoit le sujet :

- le prompt donne, pour chaque agent, son nom, son rôle secret, sa personnalité et **ce qu'il sait** (`context_for`) ;
- le modèle renvoie un JSON `{"echange": [{"auteur", "message"}], "notes": {nom: "ce qu'il retient"}}` (6 messages au plus), validé (auteurs connus, une note par agent) et redemandé si besoin ;
- enregistrement : annonce publique « Conversation privée entre … » ; chaque message en `private_summary` visible des seuls participants ; la note de chaque agent dans **sa** mémoire personnelle ;
- si l'appel échoue, seule l'annonce reste.

---

## 5. Comment tout s'enchaîne

### Mise en place : `game_engine.setup_game`

`setup_game(names, human_id, personality_names, rng)` tire les rôles et les personnalités (`assign_players`, avec le nom français de chaque personnalité lu dans son skill par `PromptLoader.personality_display_name`), choisit la fausse piste de la Voyante, crée la mémoire avec les noms (`MemoryManager(ids, names=names)`) et les agents (`create_all_agents`), puis enregistre les informations de première nuit (`first_night_info`) en `role_info`, visibles du seul joueur concerné. Elle renvoie `(state, agents, memory)`.

### Un tour

Deux versions du tour, qui suivent le même schéma :

- `ai_turns.play_turn_with_ai(state, rng, agents, memory)` : les IA jouent seules ; l'humain reçoit un choix de nuit aléatoire et ne vote pas.
- `human_turns.play_turn_with_human(state, rng, agents, memory, human_id, human, day_seconds=240)` : l'humain joue aussi. `human` respecte le protocole `HumanPort` (`night_choice`, `day_action`, `private_message`, `vote_on`…). Il est implémenté par le terminal (`scripts/play_with_human.py`) et par le WebSocket (`backend/server/game_session.py`).

```
NUIT        memory.set_moment(tour, NUIT)
            collect_ai_night_choices        agent.night_action(noms) → ids     (2 appels LLM en parallèle au plus)
            (humain : human.night_choice)
            play_night                      choix invalide ou absent → choix légal au hasard
            reveal_psychic_answer           réponse de la Voyante → sa mémoire (role_info)
            announce_night                  « Le jour N se lève. Mort cette nuit : … » (public)
            victoire ? → fin
JOUR        memory.set_moment(tour, DISCUSSION)        minuté : day_seconds
            public_conversation(agents)     les IA ouvrent la discussion
            boucle jusqu'à la fin du temps, human.day_action(...) :
              message public                → les IA répondent (public_conversation, 3 messages)
              conversation privée (1 ou 2)  → start_private_conversation / private_message
                                              + simulate_agents_conversation pour les autres agents, en parallèle
              désignation (facultative)     → vote_on_nomination, tout de suite :
                                              collect_ai_ballots (agent.vote_on) + human.vote_on
                                              resolve_nomination : exécution si les « pour » dépassent la moitié des vivants (un mort ne compte que s'il vote pour, et utilise alors son vote fantôme)
                                              announce_nomination : qui a voté pour / contre, résultat
                                              exécution → fin du jour ; sinon le jour continue
              fin de journée                → les IA peuvent encore désigner, puis fin du jour
            à la moitié du temps : collect_ai_nomination (agent.nominate, dans l'ordre de parole)
                                   et, si l'humain n'a parlé à personne, un agent lui propose une conversation
            une désignation par joueur et par jour ; un joueur n'est désigné qu'une fois par jour
VOTE        memory.set_moment(tour, VOTE)
            si personne n'a été exécuté     → final_vote : collect_ai_votes (agent.vote) + human.final_vote
                                              exécution si plus de la moitié des votes exprimés (égalité : personne)
                                              announce_vote : qui a voté pour qui, résultat
            victoire ? → fin, sinon nuit suivante
```

- **Noms et ids** : les agents reçoivent les **noms** des joueurs comme options, et `ai_turns` traduit leur réponse en **id** (les noms doivent donc être uniques).
- **Échecs** : un agent dont l'appel échoue rend un choix de nuit vide (remplacé par un choix au hasard), ne désigne personne, vote contre une désignation ou s'abstient au vote de fin de jour.
- **Ordre** : chaque étape attend la précédente ; l'humain n'écrit jamais pendant un appel IA. Les morts peuvent encore parler et voter (vote fantôme), mais pas désigner.
- **Qui écrit dans la mémoire** : `conversations.py` pour les messages, `reveal_psychic_answer` pour la Voyante, `announce_*` (`game_engine`) pour les annonces du Maître du Jeu, `vote_on_nomination` (`ai_turns`) pour la désignation, `setup_game` pour la première nuit. Les agents, eux, n'écrivent jamais dans la mémoire : ils renvoient un résultat.

### Parties dans le terminal

`scripts/play_real_game.py` (les IA seules) et `scripts/play_with_human.py` (avec un humain au clavier) jouent des parties complètes avec les vrais modèles.

---

## 6. Ce qui n'est pas dans ces modules

| Sujet | Où |
|---|---|
| Choix légaux, effets des pouvoirs, nuit, vote, Majordome, victoire, informations de la première nuit | `backend/rules` |
| État de la partie (vivants / morts, rôles réels, effets) | `backend/models` (`GameState`, `Player`, `Role`) |
| Tirage des rôles et des personnalités | `backend/rules` (`assign_players`) |
| Mise en place, nuit, vote, victoire | `game_engine` |
| Déroulement d'un tour avec les IA / avec l'humain | `ai_turns`, `human_turns` |
| Chargement des skills | `prompt_loader` |
| Lien avec le front, choix de l'humain | `server`, `static/` |

## 7. Points encore ouverts

- **Agent et état du joueur** : `Player` est immuable, donc `agent.player` reste celui de la création (il ne voit pas sa mort). Pour l'état actuel, lire `GameState`.

## 8. Limites connues

- Le contexte grandit à chaque événement (environ 1 900 à 2 800 tokens par appel dans une phase de discussion) : prévoir un **résumé par jour** pour les longues parties.
- Les personnalités non obligées passent rarement leur tour, même avec l'instruction renforcée (essai avec les vrais modèles : 1 tour passé sur 8 tours facultatifs). Si l'Observateur doit parler moins, le code devra décider à sa place (par exemple lui donner la parole un tour sur deux).

## 9. Tests

```
python -m pytest tests/ -q
```

| Fichier | Vérifie surtout |
|---|---|
| `tests/test_memory_manager.py`, `tests/test_memory_names.py` | L'**isolation** : un joueur ne voit jamais un événement qui ne lui est pas destiné ; datation par `set_moment` ; noms affichés à la place des ids |
| `tests/test_agent_factory.py` | Prompt (noms des joueurs), actions de nuit, votes, désignation, vote pour/contre, choix illégaux redemandés, `PASSE` et ses variantes |
| `tests/test_conversations.py` | Ordre de parole, limite de 10 messages, fin quand tout le monde passe, secret du privé, agent en échec, conversation simulée entre agents |
| `tests/test_vote.py`, `tests/test_announcements.py` | Vote pour/contre une désignation (majorité, Majordome, vote fantôme), annonces du Maître du Jeu, textes de première nuit |
| `tests/test_game_session.py` | Parties complètes par le WebSocket avec de faux agents : jour minuté, désignation, proposition d'un agent, conversation privée, route admin |
| `tests/test_ai_turns.py` | Traduction noms ↔ ids, agent en échec, désignation dans l'ordre de parole, vote de fin de jour quand personne n'est exécuté sur désignation, tour complet avec les IA |

Les tests utilisent un **faux LLM** : aucun appel réseau. Lancer depuis la racine du projet.
