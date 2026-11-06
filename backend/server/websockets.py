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
                
                action = action_packet.action
                payload = action_packet.payload
                
                logger.info(f"Action reçue de {player_id} -> Type: {action} | Payload: {payload}")
                
                # 1. GESTION DU CHAT
                if action == "send_chat":
                    channel_id = payload.channel_id
                    content = payload.content
                    
                    chat_packet = {
                        "type": "chat",
                        "channel_id": channel_id,
                        "sender": player_id,
                        "content": content
                    }
                    
                    if channel_id == "public":
                        # Diffusion à tout le monde
                        await manager.broadcast(chat_packet)
                    else:
                        # Salon privé / Chuchotement (envoyé aux participants du canal)
                        await manager.send_to_player(player_id, chat_packet)
                        if channel_id != player_id:
                            await manager.send_to_player(channel_id, chat_packet)

                # 2. DEMANDE DE CONVERSATION PRIVÉE
                elif action == "request_whisper":
                    targets = payload.targets
                    logger.info(f"Joueur {player_id} souhaite discuter en privé avec les agents : {targets}")
                    
                    if len(targets) == 0 or len(targets) > 2:
                        await manager.send_to_player(
                            player_id,
                            {"type": "error", "data": "Vous devez sélectionner 1 ou 2 agents maximum pour une discussion privée."}
                        )
                    else:
                        # Création d'un ID de canal unique trié (ex: whisper_Ariel_agent_bot_1)
                        participants = sorted([player_id] + targets)
                        channel_id = "whisper_" + "_".join(participants)
                        
                        # 1. Annonce publique dans le chat pour tout le monde
                        announcement_text = f"💬 {player_id} est entré en discussion privée avec {', '.join(targets)}."
                        await manager.broadcast({
                            "type": "chat",
                            "channel_id": "public",
                            "sender": "Grimoire",
                            "content": announcement_text
                        })
                        
                        # 2. Ouverture effective du canal privé pour l'humain (et préparation pour les agents)
                        await manager.send_to_player(
                            player_id,
                            {
                                "type": "private_channel_opened",
                                "channel_id": channel_id,
                                "members": participants,
                                "text": f"Salon privé ouvert avec {', '.join(targets)}"
                            }
                        )

                # 3. RÉPONSE À UNE INVITATION DE CONVERSATION PRIVÉE
                elif action == "respond_whisper_invitation":
                    target_agent_id = payload.target_agent_id
                    accepted = payload.accepted
                    
                    logger.info(f"Joueur {player_id} a répondu à l'invitation de {target_agent_id} -> Accepté: {accepted}")
                    
                    if accepted:
                        await manager.send_to_player(
                            player_id,
                            {
                                "type": "announcement",
                                "text": f"Canal privé ouvert avec {target_agent_id}."
                            }
                        )
                        # TODO: Notifier le moteur de jeu / l'agent IA de démarrer la conversation privée
                    else:
                        pass

                # 4. SOUMISSION DU VOTE
                elif action == "submit_vote":
                    target_id = payload.target_id
                    logger.info(f"Vote enregistré pour {player_id} -> Cible : {target_id}")
                    
                    await manager.send_to_player(
                        player_id, 
                        {
                            "type": "announcement", 
                            "text": f"Votre vote pour '{target_id or 'personne'}' a bien été pris en compte."
                        }
                    )
                    # TODO: Transmettre au game_engine pour centraliser les votes du village

                # 5. ACTIONS DE NUIT
                elif action == "submit_night_action":
                    targets = payload.targets # Liste de cibles de nuit
                    logger.info(f"Action de nuit reçue de {player_id} avec {len(targets)} cible(s) : {targets}")
                    
                    if len(targets) > 2:
                        await manager.send_to_player(
                            player_id,
                            {"type": "error", "data": "Vous ne pouvez pas cibler plus de 2 joueurs."}
                        )
                    else:
                        await manager.send_to_player(
                            player_id,
                            {
                                "type": "announcement",
                                "text": "Vos choix nocturnes ont été enregistrés."
                            }
                        )
                        # TODO: Transmettre les cibles au game_engine pour la résolution nocturne

                else:
                    logger.warning(f"Action non reconnue reçue de {player_id}: {action}")

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