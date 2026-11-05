import json
import logging
from typing import Dict, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gère l'ensemble des connexions WebSocket actives pour les joueurs."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, player_id: str, websocket: WebSocket) -> None:
        """Accepte la connexion WebSocket d'un joueur et l'enregistre."""
        await websocket.accept()
        self.active_connections[player_id] = websocket
        logger.info(f"Joueur connecté : {player_id}. Total connexions : {len(self.active_connections)}")

    def disconnect(self, player_id: str) -> None:
        """Retire un joueur de la liste des connexions actives lors de sa déconnexion."""
        if player_id in self.active_connections:
            del self.active_connections[player_id]
            logger.info(f"Joueur déconnecté : {player_id}. Total connexions : {len(self.active_connections)}")


    async def send_to_player(self, player_id: str, message: dict[str, Any]) -> None:
        """
        Envoie un message JSON ciblé à un joueur spécifique.
        Utile pour : les infos de nuit secrètes, les salons privés, ou les erreurs.
        """
        websocket = self.active_connections.get(player_id)
        if websocket:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi au joueur {player_id}: {e}")
                self.disconnect(player_id)
        else:
            logger.warning(f"Tentative d'envoi à un joueur non connecté ou introuvable : {player_id}")


    # Pas nécessaire pour l'instant car jeu solo, mais en place pour l'évolutivité
    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Diffuse un message JSON à tous les joueurs connectés en même temps.
        Utile pour : les mises à jour globales du GameState ou le tchat public.
        """
        if not self.active_connections:
            return

        disconnected_players = []
        payload = json.dumps(message)

        for player_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(payload)
            except Exception as e:
                logger.error(f"Erreur lors du broadcast vers {player_id}: {e}")
                disconnected_players.append(player_id)

        for player_id in disconnected_players:
            self.disconnect(player_id)


manager = ConnectionManager()