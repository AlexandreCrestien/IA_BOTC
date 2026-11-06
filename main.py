from backend.server.game_runner import start_game

GAME_CONFIG = {
    "names": {"player_human_1": "Alex", "ia_1": "Ariel", "ia_2": "Bob"},  # à compléter
    "human_id": "player_human_1",
    "personality_names": [],  # à remplir avec les personnalités de tests/test_human_turns.py
}


@app.post("/game/start", tags=["Partie"])
async def demarrer_partie():
    start_game(**GAME_CONFIG)
    return {"status": "started"}