"""Simule la partie sans appel LLM, pour vérifier que serveur, moteur et messages sont reliés.

- Les appels IA renvoient une réponse fixe (aucun réseau, aucun quota).
- Le joueur humain est joué automatiquement : vote, nuit, message public, salon privé.
- Chaque message reçu par le front est affiché.

Lancement depuis la racine du projet :
    python scripts/simulate_ai.py
Si la partie se termine sans plus de message, arrête avec Ctrl+C (la lecture WebSocket attend).
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from backend import llm_client  # noqa: E402
from backend.server.app import app, GAME_CONFIG  # noqa: E402

HUMAN = GAME_CONFIG["human_id"]
MAX_MESSAGES = 300  # garde-fou pour ne pas tourner indéfiniment

# 1. Pas de pause entre appels : la simulation doit être rapide.
llm_client.CALL_PAUSE_SECONDS = 0


# 2. Faux routeur : même forme de réponse que LiteLLM, sans réseau.
async def fake_acompletion(model, messages, **kwargs):
    wants_json = kwargs.get("response_format") is not None
    content = "{}" if wants_json else "Message simulé."
    return SimpleNamespace(
        model=f"simulated/{model}",
        usage=SimpleNamespace(total_tokens=0),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


llm_client.router.acompletion = fake_acompletion


def send(ws, packet):
    ws.send_text(json.dumps(packet))


def answer(ws, msg, state):
    """Réponse automatique du joueur humain à chaque demande du serveur."""
    kind = msg.get("kind")
    data = msg.get("data", {})

    if msg["type"] == "vote_request":
        targets = data.get("targets", [])
        send(ws, {"action": "submit_vote", "payload": {"target_id": targets[0] if targets else ""}})

    elif msg["type"] == "night_request":
        count = data.get("count", 1)
        send(ws, {"action": "submit_night_action",
                  "payload": {"targets": data.get("targets", [])[:count]}})

    elif kind == "public_message":
        send(ws, {"action": "send_chat",
                  "payload": {"channel_id": "public", "content": "Bonjour, je suis l'humain."}})

    elif kind == "private_partners":
        choices = data.get("choices", [])
        if choices:
            send(ws, {"action": "request_whisper", "payload": {"targets": choices[:1]}})

    elif kind == "private_message" and state["channel"]:
        send(ws, {"action": "send_chat",
                  "payload": {"channel_id": state["channel"], "content": "Que sais-tu ?"}})


def main():
    state = {"channel": None}
    counts = {}

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/{HUMAN}") as ws:
            print("POST /game/start ->", client.post("/game/start").json())

            for _ in range(MAX_MESSAGES):
                msg = json.loads(ws.receive_text())
                key = msg.get("kind") or msg.get("type")
                counts[key] = counts.get(key, 0) + 1
                print(f"[{key}]", json.dumps(msg, ensure_ascii=False)[:200])

                if msg.get("type") == "private_channel_opened":
                    state["channel"] = msg["channel_id"]

                if msg.get("type") in ("vote_request", "night_request", "engine_request"):
                    answer(ws, msg, state)

    print("\nRésumé des messages reçus :")
    for key, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {key} : {n}")


if __name__ == "__main__":
    main()