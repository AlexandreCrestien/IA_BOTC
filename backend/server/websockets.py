import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError, TypeAdapter

from backend.server.connection_manager import manager
from backend.server.game_session import GameSession
from backend.server.schemas import ClientActionPacket

logger = logging.getLogger(__name__)

router = APIRouter()

action_validator = TypeAdapter(ClientActionPacket)

# Fabrique de sessions : remplacée dans les tests pour ne pas appeler de vrai LLM.
session_factory = GameSession


@router.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    """
    Endpoint WebSocket du joueur humain. player_id sert aussi de pseudo dans la partie.
    URL de connexion : ws://<serveur>/ws/Sasha
    L'action "start_game" lance une partie ; les autres actions répondent aux demandes du moteur.
    """
    await manager.connect(player_id, websocket)
    session: Optional[GameSession] = None
    task: Optional[asyncio.Task] = None

    async def send(message: dict) -> None:
        await manager.send_to_player(player_id, message)

    try:
        while True:
            raw_data = await websocket.receive_text()

            try:
                data_dict = json.loads(raw_data)
                action_packet = action_validator.validate_python(data_dict)
                logger.info(f"Action reçue de {player_id} -> Type: {action_packet.action}")

                if action_packet.action == "start_game":
                    if task is not None:
                        task.cancel()
                    session = session_factory(player_id, send)
                    task = asyncio.create_task(session.run())
                elif session is None or session.finished:
                    await send({"type": "error", "data": "Aucune partie en cours : lance une partie."})
                else:
                    session.inbox.put_nowait(action_packet)

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
    finally:
        if task is not None:
            task.cancel()
