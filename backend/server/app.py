import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.server.websockets import router as ws_router
from backend.server.admin import router as admin_router

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


@app.get("/health", tags=["Health Check"])
def health_check():
    """Route de santé pour vérifier rapidement si le serveur tourne."""
    return {"status": "online", "message": "Le serveur Blood on the Clocktower tourne à merveille !"}


class NoCacheStaticFiles(StaticFiles):
    """Fichiers de l'interface : le navigateur doit toujours vérifier s'il y a une nouvelle version,
    sinon il garde un ancien app.js après une modification."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", NoCacheStaticFiles(directory="static", html=True), name="static")