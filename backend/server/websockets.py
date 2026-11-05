import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError, TypeAdapter

from backend.server.connection_manager import manager
from backend.server.schemas import ClientActionPacket

logger = logging.getLogger(__name__)

router = APIRouter()

action_validator = TypeAdapter(ClientActionPacket)


@router.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    """
    Endpoint WebSocket principal pour le joueur connecté.
    URL de connexion : ws://<serveur>/ws/player_human_1
    """
    await manager.connect(player_id, websocket)
    
    try:
        while True:
            raw_data = await websocket.receive_text()
            
            try:
                data_dict = json.loads(raw_data)
                
                action_packet = action_validator.validate_python(data_dict)
                
                logger.info(f"Action reçue de {player_id} -> Type: {action_packet.action}")
                
                # TODO: Relayer l'action validée vers le backend/game_engine.py
                # Exemple : 
                # response = game_engine.handle_player_action(player_id, action_packet)
                # await manager.send_to_player(player_id, response)

            except json.JSONDecodeError:
                logger.warning(f"Message JSON invalide reçu de {player_id}")
                await manager.send_to_player(
                    player_id, 
                    {"type": "error", "data": "Format JSON invalide."}
                )

            except ValidationError as e:
                logger.warning(f"Erreur de validation de l'action pour {player_id}: {e.errors()}")
                await manager.send_to_player(
                    player_id, 
                    {"type": "error", "data": f"Action non valide : {e.errors()}"}
                )

    except WebSocketDisconnect:
        manager.disconnect(player_id)
        logger.info(f"Déconnexion propre de la WebSocket pour le joueur : {player_id}")