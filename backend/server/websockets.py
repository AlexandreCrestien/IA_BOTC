from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
from backend.server.connection_manager import manager
from backend.server.schemas import ClientActionPacket

router = APIRouter()

@router.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    await manager.connect(player_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            raw_data = json.loads(data)
            action = ClientActionPacket(**raw_data)
            
            # TODO: Relayer l'action vers backend/game_engine.py
            print(f"Action reçue de {player_id}: {action.action}")

    except WebSocketDisconnect:
        manager.disconnect(player_id)