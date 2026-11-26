"""Simule une partie sans appel LLM et affiche chaque message reçu par le front.

- Les IA répondent en mode simulation (SIMULATE_LLM=1 : aucun réseau, aucun quota).
- Le joueur humain est joué automatiquement : action de nuit, message public, salon privé, vote.
- Utile pour voir rapidement ce que le serveur envoie au front pendant une partie entière.
  Pour un contrôle détaillé (avec vérifications), voir scripts/check_full_game.py.

Lancement depuis la racine du projet :
    python scripts/simulate_game.py
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SIMULATE_LLM"] = "1"  # doit être défini avant l'import de llm_client
os.environ["DATABASE_URL"] = "sqlite://"  # base en mémoire : la vraie base n'est pas touchée

from fastapi.testclient import TestClient  # noqa: E402

from backend.ai import llm_client  # noqa: E402
from backend.server.app import app  # noqa: E402

llm_client.CALL_PAUSE_SECONDS = 0  # pas de pause entre les appels simulés

HUMAN = "Simulateur"  # pseudo du joueur humain
MAX_MESSAGES = 5000  # garde-fou pour ne pas tourner indéfiniment


def send(ws, action, payload=None):
    ws.send_text(json.dumps({"action": action, "payload": payload or {}}))


def answer(ws, msg):
    """Réponse automatique du joueur humain, comme s'il cliquait dans le front."""
    if msg["type"] == "action_request":
        candidates = [c for c in msg["candidates"] if c != HUMAN]
        if msg["kind"] == "vote":
            send(ws, "submit_vote", {"target_id": candidates[0] if candidates else None})
        elif msg["kind"] == "nuit":
            send(ws, "submit_night_action", {"targets": msg["candidates"][: msg.get("min_targets", 1)]})
        elif msg["kind"] == "discussion":
            send(ws, "request_whisper", {"targets": candidates[:1]})

    elif msg["type"] == "input_request":
        if msg["kind"] == "public_message":
            send(ws, "send_chat", {"channel_id": "public", "content": "Bonjour, je suis l'humain."})
        elif msg["kind"] == "private_message":
            send(ws, "send_chat", {"channel_id": msg["channel_id"], "content": "Que sais-tu ?"})


def main():
    counts = Counter()
    # « with » : une seule boucle asyncio, comme avec le vrai serveur
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/{HUMAN}") as ws:
            for _ in range(MAX_MESSAGES):
                msg = json.loads(ws.receive_text())
                counts[msg["type"]] += 1
                shown = {k: v for k, v in msg.items() if k != "state"}  # l'état complet est trop long
                print(f"[{msg['type']}]", json.dumps(shown, ensure_ascii=False)[:200])
                answer(ws, msg)
                if msg["type"] in ("game_over", "game_interrupted"):
                    break

    print("\nRésumé des messages reçus :")
    for kind, n in counts.most_common():
        print(f"  {kind} : {n}")


if __name__ == "__main__":
    main()
