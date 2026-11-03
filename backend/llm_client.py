from dotenv import load_dotenv
from litellm import Router

load_dotenv()

# Ordre de priorité : voir docs/choix_des_modeles.md
FAST_MODELS = [
    "gemini/gemini-3.1-flash-lite",
    "groq/openai/gpt-oss-20b",
    "openrouter/mistralai/mistral-small-24b-instruct-2501",
    "groq/openai/gpt-oss-120b",
    "openrouter/meta-llama/llama-3.1-8b-instruct",
    "openrouter/mistralai/mistral-nemo",
]

CAPABLE_MODELS = [
    "groq/openai/gpt-oss-120b",
    "gemini/gemini-3.1-flash-lite",
    "openrouter/deepseek/deepseek-v4.1-flash-1017",
    "groq/openai/gpt-oss-20b",
    "openrouter/z-ai/glm-5.3-flash",
    "gemini/gemini-3.5-flash-lite",
    "openrouter/xiaomi/mimo-v2.6-flash",
]

PROFILES = {
    "fast": {"models": FAST_MODELS, "timeout": 10, "max_tokens": 1000},
    "capable": {"models": CAPABLE_MODELS, "timeout": 25, "max_tokens": 2000},
}


def build_model_list_and_fallbacks():
    model_list = []
    fallbacks = []
    for profile_name, config in PROFILES.items():
        nicknames = []
        for position, model in enumerate(config["models"], start=1):
            nickname = f"{profile_name}-{position}"
            nicknames.append(nickname)
            model_list.append({
                "model_name": nickname,
                "litellm_params": {
                    "model": model,
                    "timeout": config["timeout"],
                    "max_tokens": config["max_tokens"],
                },
            })
        fallbacks.append({nicknames[0]: nicknames[1:]})
    return model_list, fallbacks


_model_list, _fallbacks = build_model_list_and_fallbacks()

router = Router(
    model_list=_model_list,
    fallbacks=_fallbacks,
    num_retries=1,
    allowed_fails=2,
    cooldown_time=60,
)


async def ask_llm(profile: str, messages: list[dict]) -> str:
    """Envoie les messages au premier modèle du profil ("fast" ou "capable") et renvoie le texte.

    Si tous les modèles du profil échouent, l'exception remonte : c'est à l'appelant
    (l'orchestrateur) de prendre une décision par défaut.
    """
    response = await router.acompletion(model=f"{profile}-1", messages=messages)
    content = response.choices[0].message.content
    if not content:
        # Arrive avec les modèles de raisonnement quand max_tokens est épuisé avant la réponse
        raise ValueError(f"Réponse vide du modèle {response.model}")
    return content
