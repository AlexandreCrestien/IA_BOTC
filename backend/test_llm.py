import json
import time

from dotenv import load_dotenv
from litellm import completion, completion_cost

load_dotenv()

list_of_models = [
    "groq/openai/gpt-oss-120b",
    "groq/openai/gpt-oss-20b",
    "gemini/gemini-3.1-flash-lite",
    "openrouter/deepseek/deepseek-v4.1-flash-1017",
]
PROMPT = "Choisis un joueur à éliminer parmi [Alex, Flora, Edilene]. Réponds uniquement en JSON avec les champs cible et raison."
RUNS_PER_MODEL = 3
PAUSE_SECONDS = 1


def test_model(model_name):
    start = time.perf_counter()
    try:
        response = completion(
            model=model_name,
            messages=[{"role": "user", "content": PROMPT}],
        )
    except Exception as e:
        duration = time.perf_counter() - start
        print(f"❌ {model_name} | {duration:.2f}s | {type(e).__name__}: {str(e)[:120]}")
        return

    duration = time.perf_counter() - start
    try:
        cost = completion_cost(completion_response=response)
    except Exception:
        cost = None

    content = response.choices[0].message.content
    try:
        data = json.loads(content)
        if {"cible", "raison"} <= data.keys():
            verdict = "JSON OK"
        else:
            verdict = f"JSON avec les bons champs: {list(data.keys())}"
    except (json.JSONDecodeError, AttributeError, TypeError):
        verdict = "JSON INVALIDE"

    print(
        f"✅ {model_name} | {duration:.2f}s | tokens: {response.usage.total_tokens} | coût: {cost} | {verdict}\n"
        f"   ➡️  {content}"
    )


if __name__ == "__main__":
    for model_name in list_of_models:
        for _ in range(RUNS_PER_MODEL):
            test_model(model_name)
            time.sleep(PAUSE_SECONDS)
