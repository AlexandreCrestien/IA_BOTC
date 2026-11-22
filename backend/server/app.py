import asyncio
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.accounts.service import ensure_admin
from backend.db import get_session, init_db
from backend.server.account_removal import purge_periodically
from backend.server.auth import router as auth_router
from backend.server.game_routes import router as game_router
from backend.server.stats_routes import router as stats_router
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
    création du compte admin s'il n'existe pas (ADMIN_PSEUDO / ADMIN_PASSWORD du .env), puis suppression
    des comptes inactifs depuis un an (maintenant, puis une fois par jour)."""
    init_db()
    with get_session() as db:
        ensure_admin(db)
    purge = asyncio.create_task(purge_periodically())
    yield
    purge.cancel()


app = FastAPI(
    title="Lantern Hollow - Backend API",
    description="API en temps réel (websockets) pour lier le moteur de jeu Python et le frontend.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(game_router)
app.include_router(stats_router)
app.include_router(admin_router)

# --- Page introuvable ------------------------------------------------------------------
# Une page demandée par le navigateur reçoit la page 404 du jeu ; les routes de l'API
# (/api/…, /admin/…) gardent leur réponse JSON, lue par le front pour ses messages d'erreur ;
# un fichier manquant (script, style, image) reçoit une simple 404.
# Le fichier ne s'appelle pas 404.html : StaticFiles le servirait lui-même pour toute adresse inconnue,
# y compris celles de l'API.
NOT_FOUND_PAGE = os.path.join("static", "not-found.html")
API_PREFIXES = ("/api/", "/admin/", "/ws/")


def wants_not_found_page(request: Request) -> bool:
    path = request.url.path
    if path.startswith(API_PREFIXES):
        return False
    last = path.rsplit("/", 1)[-1]
    if "." in last and not last.endswith(".html"):
        return False
    return "text/html" in request.headers.get("accept", "")


@app.exception_handler(StarletteHTTPException)
async def not_found_page(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and wants_not_found_page(request):
        return FileResponse(NOT_FOUND_PAGE, status_code=404)
    return await http_exception_handler(request, exc)


@app.get("/admin", tags=["Administration UI"])
def serve_admin_page():
    """Sert la page HTML du panneau de contrôle admin."""
    return FileResponse(os.path.join("static", "admin.html"))

@app.get("/health", tags=["Health Check"])
def health_check():
    """Route de santé pour vérifier rapidement si le serveur tourne."""
    return {"status": "online", "message": "Le serveur Lantern Hollow tourne à merveille !"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")