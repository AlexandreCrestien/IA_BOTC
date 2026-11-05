import os
import logging
import secrets
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status, Depends
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Administration"])

ADMIN_SECRET_TOKEN = os.getenv("ADMIN_SECRET_TOKEN")

def verify_admin_token(x_admin_token: Optional[str] = Header(default=None)):
    """Vérifie que la requête contient le bon jeton secret dans le header.
    Si aucun jeton n'est configuré (variable absente ou vide), l'accès admin est toujours refusé.
    Header absent ou jeton faux : même réponse 403.
    compare_digest compare en temps constant : le temps de réponse ne révèle rien du jeton.
    On compare des octets : avec du texte, un caractère non ASCII ferait planter la comparaison."""
    if not ADMIN_SECRET_TOKEN or not x_admin_token or not secrets.compare_digest(x_admin_token.encode(), ADMIN_SECRET_TOKEN.encode()):
        logger.warning("Tentative d'accès admin non autorisée détectée.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : Jeton admin invalide ou manquant."
        )
    return x_admin_token


@router.get("/debug/all-states", dependencies=[Depends(verify_admin_token)])
def get_all_debug_states():
    """
    Route sécurisée pour récupérer l'inspection totale du jeu :
    - Historique des tchats publics et privés
    - État interne et mémoire des agents IA
    - Historique des nuits de tout le monde
    """
    # TODO: Connecter cette route au moteur de jeu global
    # Exemple de structure de retour pour le dashboard de débug :
    # return {
    #     "status": "success",
    #     "message": "Bienvenue dans l'espace admin de Blood on the AI Clocktower",
    #     "public_chat_history": [],
    #     "private_channels": [],
    #     "agents_private_logs": {}
    # }