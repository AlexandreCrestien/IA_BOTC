import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.accounts.service import ensure_admin
from backend.db import get_session, init_db
from backend.server.auth import router as auth_router
from backend.server.game_routes import router as game_router
from backend.server.websocket_endpoint import router as ws_router
from backend.server.admin import router as admin_router
# Chargé dès le démarrage (moteur de jeu, LiteLLM : quelques secondes) plutôt qu'à la première
# connexion d'un joueur, qui attendrait sinon devant l'écran d'accueil.
import backend.server.game_runner  # noqa: E402,F401

# Configuration des logs pour avoir un suivi propre dans la console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Au démarrage : ouverture de la base (création des tables, parties restées en cours interrompues),
    puis création du compte admin s'il n'existe pas (ADMIN_PSEUDO / ADMIN_PASSWORD du .env)."""
    init_db()
    with get_session() as db:
        ensure_admin(db)
    yield


app = FastAPI(
    title="Lantern Hollow - Backend API",
    description="API en temps réel (websockets) pour lier le moteur de jeu Python et le frontend.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(game_router)
app.include_router(admin_router)

@app.get("/admin", tags=["Administration UI"])
def serve_admin_page():
    """Sert la page HTML du panneau de contrôle admin."""
    return FileResponse(os.path.join("static", "admin.html"))

@app.get("/health", tags=["Health Check"])
def health_check():
    """Route de santé pour vérifier rapidement si le serveur tourne."""
    return {"status": "online", "message": "Le serveur Lantern Hollow tourne à merveille !"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")