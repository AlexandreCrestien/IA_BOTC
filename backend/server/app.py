import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.server.websockets import router as ws_router
from backend.server.admin import router as admin_router
from backend.server.connection_manager import manager
from backend.server.game_runner import start_game

# Configuration des logs pour avoir un suivi propre dans la console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Blood on the AI Clocktower - Backend API",
    description="API en temps réel (websockets) pour lier le moteur de jeu Python et le frontend.",
    version="1.0.0"
)

# Configuration CORS (nécessaire si le frontend tourne sur un autre port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(admin_router)

GAME_CONFIG = {
    "names": {
        "Sasha": "Sasha",
        "p1": "marIA",
        "p2": "tobIAs",
        "p3": "mAIsie",
        "p4": "adrIAn",
        "p5": "dIAne",
    },
    "human_id": "Sasha",
    "personality_names": ["agitator", "clown", "observer", "paranoid", "strategist"],
}


@app.get("/health", tags=["Health Check"])
def health_check():
    """Route de santé pour vérifier rapidement si le serveur tourne."""
    return {"status": "online", "message": "Le serveur Blood on the Clocktower tourne à merveille !"}


@app.post("/game/start", tags=["Partie"])
async def demarrer_partie():
    if GAME_CONFIG["human_id"] not in manager.active_connections:
        return {"status": "error", "detail": "Le joueur humain doit être connecté avant de lancer la partie."}
    start_game(**GAME_CONFIG)
    return {"status": "started"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")