# Architecture IA : `llm_client`, `memory_manager` et `agent_factory`

*Partie « AI & Memory Architect ». Ce document décrit les trois modules, ce que chacun fait, et comment ils s'enchaînent.*

## Vue d'ensemble

Chaque module a une seule responsabilité :

| Module | Responsabilité | Ne fait jamais |
|---|---|---|
| `backend/llm_client.py` | **Comment** parler aux modèles (choix du modèle, fallback, JSON) | Rien de spécifique au jeu |
| `backend/memory_manager.py` | **Ce que** chaque joueur sait (qui a vu quoi) | Appeler un LLM, décider des règles |
| `backend/agent_factory.py` | **Assembler** un personnage IA : prompt + mémoire + LLM | Enregistrer dans la mémoire, décider ce qui est légal |

Les dépendances vont dans un seul sens :

```
agent_factory ──► memory_manager
      │
      ├────────► prompt_loader ──► skills/*.md
      │
      └────────► llm_client ──► LiteLLM (Groq, Gemini, OpenRouter)
```

`memory_manager` et `llm_client` ne se connaissent pas. Seul `agent_factory` les relie.

---

## 1. `llm_client.py` : la seule porte vers les LLM

**Règle :** aucun autre fichier du projet n'importe `litellm`. Tout passe par ce module.

### Profils et fallback

Le code ne demande jamais un modèle précis, mais un **profil** :

| Profil | Usage | Timeout | `max_tokens` |
|---|---|---|---|
| `"fast"` | Messages du salon public, conversations privées | 10 s | 1000 |
| `"capable"` | Actions de nuit, nominations, votes | 25 s | 2000 |

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

**Si tous les modèles échouent**, l'exception remonte. C'est à l'appelant (l'orchestrateur) de prendre une décision par défaut, par exemple une action légale au hasard. Attraper `Exception` de façon générale : le type exact varie selon la dernière erreur de la chaîne.

### Logs

Chaque appel écrit une ligne `INFO` : profil, modèle qui a vraiment répondu, durée, tokens. Pour les voir :

```python
import logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("backend.llm_client").setLevel(logging.INFO)
```

---

## 2. `memory_manager.py` : qui sait quoi

### Principe

Toute information de la partie est un **événement** (`Event`), et chaque événement indique **qui peut le voir** (`visible_to`). La mémoire est la liste chronologique des événements ; ce qu'un joueur sait, c'est cette liste **filtrée** pour lui.

### `Event`

Modèle Pydantic **figé** (`frozen=True`) : on ne peut pas modifier un événement après sa création.

| Champ | Type | Sens |
|---|---|---|
| `day` | `int` | Numéro du jour / de la nuit |
| `phase` | `Phase` | `night` ou `day` |
| `type` | `EventType` | `announcement`, `death`, `public_message`, `private_meeting`, `private_summary`, `nomination`, `vote`, `night_action`, `night_info`, `role_info` |
| `author` | `str` | Id d'un joueur, ou `game_master` |
| `content` | `str` | Le texte de l'événement |
| `visible_to` | `frozenset[str] \| None` | `None` = tout le monde ; sinon, les ids qui peuvent le voir |

### Qui voit quoi

| Événement | Visible par | Méthode |
|---|---|---|
| Annonce, mort, message public, nomination, vote, « A et B ont discuté » | Tous | `add_public` |
| Contenu d'une conversation privée, alliance entre démons | Les participants | `add_private` |
| Action de nuit, information de nuit, rôle | Un seul joueur | `add_personal` |
| Leurre de la Voyante, joueur empoisonné, vrais rôles | **Personne** : c'est l'état du jeu, pas la mémoire | — |

La mémoire **ne décide pas** si une information est vraie ou fausse (empoisonnement, leurre) : elle enregistre ce que l'orchestrateur lui donne.

### Méthodes de `MemoryManager(player_ids)`

| Méthode | Rôle |
|---|---|
| `advance_phase()` | Nuit N → Jour N → Nuit N+1. La partie commence à la nuit 1. |
| `add_event(type, author, content, visible_to)` | Fonction générique. Si l'auteur est un joueur, il est ajouté automatiquement aux lecteurs. |
| `add_public` / `add_private` / `add_personal` | Raccourcis qui fixent `visible_to`. |
| `events_for(player)` | **Seule façon de lire la mémoire** : les événements visibles par ce joueur, dans l'ordre. Renvoie une nouvelle liste. |
| `context_for(player)` | Les mêmes événements, sous forme de texte en français pour le prompt. |

### Protections (lèvent `ValueError`)

- ids de joueurs en double, ou joueur nommé `game_master` ;
- auteur inconnu ;
- lecteur inconnu, ou liste de lecteurs vide ;
- lecture par un joueur inconnu.

### Exemple de `context_for("ana")`

```
[Nuit 1] (personnel) Maître du Jeu : Tu es le Moine.
[Nuit 1] (personnel) Toi : Je protège bruno.
[Jour 1] (public) Maître du Jeu : Le jour 1 commence. Personne n'est mort.
[Jour 1] (public) carla : Bonjour à tous !
[Jour 1] (privé avec bruno) Toi : Ana et Bruno soupçonnent carla.
```

Le canal (`public` / `personnel` / `privé avec …`) aide l'agent à ne pas répéter en public ce qu'il a appris en privé.

---

## 3. `agent_factory.py` : les personnages IA

### Le prompt d'un agent

Construit une fois, à la création de l'agent :

1. **Base assemblée par `PromptLoader`** (`backend/prompt_loader.py`) : contexte du jeu, skill de rôle (`skills/roles/<role>.md`), skill de personnalité (`skills/personalities/<personnalité>.md`) et règles générales (`skills/general_rules.md`, dont la concision : 2 phrases maximum) ;
2. **`AGENT_RULES`** : règles propres aux agents IA, absentes de `general_rules.md` (première nuit sans mort, morts toujours présents, ne rien inventer, secret du privé, secret de l'allié démon, français, pas de hashtags) ;
3. la liste des joueurs présents.

À chaque appel, on ajoute un message avec **ce que l'agent sait** (`memory.context_for`) et **l'instruction du moment**.

### Méthodes de `Agent(player_id, role, personality, memory)`

| Méthode | Profil | Renvoie |
|---|---|---|
| `await speak_public()` | fast | Texte du message pour le salon public |
| `await speak_private(partners)` | fast | Réponse dans une conversation privée |
| `await night_action(options, number_of_targets=1)` | capable | Liste des cibles (2 pour la Voyante) |
| `await nominate(options)` | capable | Un joueur, ou `None` pour personne |
| `await vote(nominee)` | capable | `True` (pour l'exécution) / `False` |

- `options` = les **choix légaux**, fournis par le moteur de règles. Un choix hors des options est refusé par la validation et redemandé au modèle.
- La `raison` donnée par le modèle va **seulement dans les logs**, jamais dans la mémoire.
- Les méthodes **renvoient** un résultat : elles n'écrivent pas dans la mémoire.

### `create_agents(assignments, memory, human_id)`

Crée un agent par joueur IA à partir de `{id: (rôle, personnalité)}`. L'humain n'a pas d'agent.

---

## 4. Comment tout s'enchaîne : un tour de parole

```
game_engine (orchestrateur)
   │  « ana, c'est ton tour de parler »
   ▼
Agent ana ─────────────── agent_factory
   │ 1. memory.context_for("ana")           → memory_manager : ce qu'ana sait
   │ 2. messages = [prompt système, contexte + instruction]
   │ 3. ask_llm("fast", messages)           → llm_client → Router → modèle
   ▼
   renvoie le texte
   │
game_engine
   │ 4. memory.add_public(public_message, "ana", texte)
   ▼
tour suivant : les autres agents verront ce message dans leur contexte
```

En code :

```python
memory = MemoryManager(["ana", "bruno", "carla", "humain"])
agents = create_agents(
    {"ana": ("imp", "strategist"), "bruno": ("monk", "paranoid"),
     "carla": ("psychic", "clown"), "humain": ("butler", "observer")},
    memory,
    human_id="humain",
)

memory.add_personal(EventType.role_info, game_master, "Tu es le Diablotin.", "ana")
memory.advance_phase()  # jour 1

text = await agents["ana"].speak_public()
memory.add_public(EventType.public_message, "ana", text)
```

**C'est l'orchestrateur qui enregistre dans la mémoire**, pas l'agent : lui seul sait si le message va au salon public ou dans une conversation privée.

Pour une action de nuit :

```python
options = ...  # fourni par le rules_engine
try:
    targets = await agents["ana"].night_action(options)
except Exception:
    targets = [random.choice(options)]  # filet de sécurité : la partie continue
memory.add_personal(EventType.night_action, "ana", f"J'ai choisi {targets[0]}.", "ana")
```

---

## 5. Ce qui n'est pas dans ces modules

| Sujet | Où |
|---|---|
| Qui peut agir, choix légaux, effets des pouvoirs, vote fantôme, victoire | `rules_engine` |
| État de la partie (vivants / morts, rôles réels) | `models` |
| Boucle de jeu, timer, enregistrement dans la mémoire, tirage des rôles et personnalités, filet de sécurité | `game_engine` |
| Chargement des skills | `prompt_loader` |
| Lien avec le front | `server` |

## 6. Limites connues / à faire

- Le contexte grandit à chaque événement (environ 1 700 à 2 200 tokens par appel lors des tests) : prévoir un **résumé par jour** pour les longues parties.
- Les conversations privées simulées entre agents ne sont pas encore décidées (script ou appel LLM).
- Les agents ne voient pas encore explicitement la liste des vivants / morts : à ajouter quand `models` sera prêt (pour l'instant, les morts sont connues via les événements `death`).

## 7. Tests

```
python -m pytest tests/ -q
```

`tests/test_memory_manager.py` vérifie surtout l'**isolation** : un joueur ne voit jamais un événement qui ne lui est pas destiné. Lancer depuis la racine du projet.
