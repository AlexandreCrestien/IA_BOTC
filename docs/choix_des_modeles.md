# Choix des modèles LLM

*Tests réalisés le 3 novembre 2026 par Edilene avec un script LiteLLM (3 exécutions par modèle, appels séquentiels).*

## Fournisseurs retenus

| Fournisseur | Variable d'environnement | Remarque |
|---|---|---|
| Groq | `GROQ_API_KEY` | Très rapide, niveau gratuit avec limites par minute |
| Google AI Studio (Gemini) | `GEMINI_API_KEY` | Niveau gratuit, limites par minute et par jour |
| OpenRouter | `OPENROUTER_API_KEY` | Une seule clé pour de nombreux modèles, **mais la plupart sont payants** |

**Mistral abandonné** : il n'existe plus d'offre gratuite. Les modèles Mistral restent accessibles via OpenRouter, mais ils ont échoué au test de bluff (voir plus bas).

---

## Test 1 : présélection (« Hello, how are you? »)

Objectif : vérifier que chaque modèle répond.

- 9 modèles sur 10 ont répondu.
- `gemini/gemini-3.1-flash-lite` a renvoyé une erreur **503** (« high demand ») : surcharge temporaire chez Google, pas une erreur de code. Il a répondu normalement aux tests suivants. **Cela montre la nécessité d'un fallback vers un autre fournisseur.**

---

## Test 2 : capacité à bluffer

**Prompt :** *« Tu es le démon secret dans un jeu de déduction sociale. Un autre joueur te demande quel est ton rôle. Réponds en une phrase, sans te dévoiler. »*

Critère principal : le modèle cache-t-il son rôle de façon crédible ? (Dans le jeu, le Diablotin et l'Empoisonneur doivent mentir sans se trahir.)

| Modèle | Temps moyen | Tokens moyens | Qualité du bluff | Verdict |
|---|---|---|---|---|
| `groq/openai/gpt-oss-120b` | **0,84 s** (0,64–0,99) | 272 | ✅ Excellent, cohérent (« simple habitant ») | 🏆 Retenu |
| `gemini/gemini-3.1-flash-lite` | **0,74 s** (0,74–0,75) | **61** | ✅ Bon, très stable | 🏆 Retenu |
| `groq/openai/gpt-oss-20b` | 1,73 s (0,60–2,93) | 718 (jusqu'à 1296) | ⚠️ Moyen, parfois suspect (« l'ombre qui garde les secrets ») | Réserve |
| `openrouter/deepseek/deepseek-v4.1-flash-1017` | 4,39 s (2,94–5,14) | 268 | ✅ Bon | Réserve (payant ?) |
| `openrouter/z-ai/glm-5.3-flash` | 10,36 s (2,27–17,55) | 393 | ✅ Le plus rusé (invente un faux rôle, retourne la question) | ❌ Trop lent et irrégulier |
| `gemini/gemini-3.5-flash-lite` | **23,33 s** (22,55–24,49) | 70 | ✅ Très bon | ❌ Beaucoup trop lent pour un jeu chronométré |
| `openrouter/xiaomi/mimo-v2.6-flash` | 4,69 s (1 seule réussite) | 112 | ✅ Correct | ❌ « Requires more credits » : payant |
| `openrouter/mistralai/mistral-nemo` | 1,76 s | 57 | ❌ Se trahit (« semer le doute et la confusion ») | ❌ Écarté |
| `openrouter/meta-llama/llama-3.1-8b-instruct` | 1,43 s | 71 | ❌ Réponses hors sujet (« transports en commun ») | ❌ Écarté |
| `openrouter/mistralai/mistral-small-24b-instruct-2501` | 0,50 s | 212 | ❌ Trop suspect (« celui qui murmure à l'oreille ») | ❌ Écarté |

---

## Test 3 : sortie JSON (4 finalistes)

**Prompt :** *« Choisis un joueur à éliminer parmi [Ana, Bruno, Carla]. Réponds uniquement en JSON avec les champs cible et raison. »*

Critère : le JSON brut est-il directement exploitable (`json.loads` + champs `cible` et `raison`) ? Le test a été fait **sans prompt système et sans `response_format`**, donc dans le pire des cas.

| Modèle | JSON valide | Temps moyen | Tokens moyens | Problème observé |
|---|---|---|---|---|
| `groq/openai/gpt-oss-120b` | 2/3 | 0,78 s | 317 | 1 **refus** (« I'm sorry, but I can't help with that ») |
| `groq/openai/gpt-oss-20b` | 2/3 | **0,57 s** | 315 | 1 réponse entourée de balises ` ```json ` |
| `gemini/gemini-3.1-flash-lite` | 2/3 | 0,98 s | **60** | 1 réponse entourée de balises ` ```json ` ; choisit toujours « Bruno » |
| `openrouter/deepseek/deepseek-v4.1-flash-1017` | **3/3** | 3,14 s | 227 | Aucun, mais lent et probablement payant |

### Enseignements

1. **Les balises ` ```json `** ne sont pas graves : le contenu est correct. Il faudra demander le format JSON au fournisseur (`response_format`) et retirer les balises par sécurité avant la validation.
2. **Le refus du 120b** vient de l'absence de contexte : « éliminer quelqu'un » sans préciser qu'il s'agit d'un jeu. Le prompt système des agents devra expliquer clairement le cadre ludique. La couche LLM doit malgré tout traiter un refus comme un échec : nouvel essai, puis modèle de réserve.
3. **Gemini choisit toujours le même joueur** sans critères. En jeu, la mémoire et les soupçons dans le prompt devraient corriger ce biais ; sinon, on pourra ajuster la `temperature`.
4. Aucun finaliste n'est éliminé : toutes les erreurs observées sont corrigibles dans la couche LLM.

---

## Décision : deux profils, tous les modèles conservés

Tous les modèles testés sont conservés. Ils sont classés par ordre de priorité : la couche LLM essaie le premier, et passe au suivant en cas d'échec. Les modèles les moins bons servent de **dernier recours** : une réponse moyenne vaut mieux qu'une partie bloquée.

### Profil « rapide » (`fast` dans `backend/llm_client.py`)

Usage : messages courts du salon public, réactions. Priorité à la vitesse.

| Ordre | Modèle | Fournisseur | Pourquoi à cette place |
|---|---|---|---|
| 1 | `gemini/gemini-3.1-flash-lite` | Gemini | Le plus stable (0,74 s), très peu de tokens |
| 2 | `groq/openai/gpt-oss-20b` | Groq | Rapide, autre fournisseur que le n° 1 |
| 3 | `openrouter/mistralai/mistral-small-24b-instruct-2501` | OpenRouter | Le plus rapide (0,50 s), bluff faible |
| 4 | `groq/openai/gpt-oss-120b` | Groq | Excellent, emprunté au profil « capable » |
| 5 | `openrouter/meta-llama/llama-3.1-8b-instruct` | OpenRouter | Rapide, mais réponses peu pertinentes |
| 6 | `openrouter/mistralai/mistral-nemo` | OpenRouter | Rapide, mais se trahit en bluffant |

### Profil « capable » (`capable` dans `backend/llm_client.py`)

Usage : actions de nuit, nominations, votes, maître du jeu, résumés de mémoire. Priorité à la qualité.

| Ordre | Modèle | Fournisseur | Pourquoi à cette place |
|---|---|---|---|
| 1 | `groq/openai/gpt-oss-120b` | Groq | Meilleur compromis qualité / vitesse |
| 2 | `gemini/gemini-3.1-flash-lite` | Gemini | Bon et stable, autre fournisseur que le n° 1 |
| 3 | `openrouter/deepseek/deepseek-v4.1-flash-1017` | OpenRouter | JSON parfait (3/3), mais 3 à 5 s |
| 4 | `groq/openai/gpt-oss-20b` | Groq | Correct, irrégulier |
| 5 | `openrouter/z-ai/glm-5.3-flash` | OpenRouter | Le plus rusé, mais jusqu'à 17 s |
| 6 | `gemini/gemini-3.5-flash-lite` | Gemini | Très bon, mais environ 23 s |
| 7 | `openrouter/xiaomi/mimo-v2.6-flash` | OpenRouter | Exige des crédits |

### Pourquoi cet ordre

- **Les fournisseurs alternent en tête de liste** : quand Groq atteint sa limite par minute, *tous* ses modèles échouent en même temps. Le n° 2 de chaque profil est donc toujours chez un autre fournisseur.
- **Un fournisseur principal différent par profil** (Gemini pour « rapide » (`fast`), Groq pour « capable ») : la charge est répartie.
- **Les modèles lents sont en fin de liste** : en jeu chronométré, 23 s d'attente n'est acceptable qu'en tout dernier recours.
- **OpenRouter ne sert jamais de principal** : ses modèles sont probablement payants, et ils tombent tous ensemble quand les crédits sont épuisés.

---

## Stratégie « la partie ne doit jamais s'arrêter »

La liste de modèles ne suffit pas : il faut aussi définir **comment** et **quand** passer au suivant.

1. **Échecs qui déclenchent le passage au modèle suivant** : limite atteinte (429), service indisponible (503), délai dépassé, crédits insuffisants, JSON invalide, champs manquants, refus de répondre.
2. **Clé invalide (`AuthenticationError`)** : inutile de réessayer. Passer au suivant et le signaler clairement dans les logs.
3. **Peu de tentatives par modèle** : 1 nouvel essai au maximum sur le même modèle, puis le suivant. Insister sur un fournisseur saturé fait perdre du temps.
4. **Délai maximum par modèle** : par exemple 10 s pour « rapide » et 25 s pour « capable », sinon un seul modèle lent bloque toute la chaîne.
5. **Mise à l'écart temporaire (cooldown)** : un modèle qui vient d'échouer plusieurs fois est ignoré pendant un moment. Le `Router` de LiteLLM sait le faire (`allowed_fails`, `cooldown_time`).
6. **Budget total par appel** : même avec tous les modèles, une réponse ne doit pas dépasser une durée maximale, par exemple 30 s. Au-delà, on abandonne.
7. **Filet de sécurité final, sans LLM** : si tous les modèles échouent, l'orchestrateur prend une **décision par défaut** :
   - action de nuit ou vote : un choix aléatoire **parmi les options légales** (fournies par le moteur de règles) ;
   - message dans le salon : une phrase générique ou passer son tour.

   C'est ce dernier niveau qui garantit vraiment que la partie continue. Il peut réutiliser le mode mock.
8. **Tout journaliser** : quel modèle a réellement répondu, combien de fallbacks, combien de décisions par défaut. Si les décisions par défaut deviennent fréquentes, c'est le signe d'un problème de quota.

---

## Points d'attention

- ⚠️ **OpenRouter** : `coût: None` ne veut pas dire « gratuit », mais que LiteLLM ne connaît pas le prix du modèle. L'erreur « requires more credits » de mimo confirme que ces modèles sont payants. **Vérifier le tableau de bord OpenRouter** avant de les utiliser en jeu. Seules les variantes explicitement gratuites sont sans coût.
- **Gemini** : le coût affiché par LiteLLM est une estimation au tarif public. Avec une clé du niveau gratuit d'AI Studio, rien n'est facturé.
- **Limites des offres gratuites** : une partie complète fera des centaines d'appels. Prévoir un fallback (`Router` de LiteLLM), une limite de concurrence par fournisseur et des pauses si nécessaire.
- **Tests limités** : 3 exécutions par modèle seulement, et des prompts sans contexte de jeu. À refaire avec les vrais prompts des agents une fois les skills écrits.
