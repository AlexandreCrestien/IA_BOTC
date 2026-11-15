import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError, TypeAdapter

from backend.front_state import to_front_state
from backend.server.connection_manager import manager
from backend.server.schemas import ClientActionPacket

logger = logging.getLogger(__name__)

router = APIRouter()

action_validator = TypeAdapter(ClientActionPacket)

# Par joueur humain : port du moteur, demande en attente de réponse, salon privé ouvert.
ports: dict[str, Any] = {}
pending: dict[str, str] = {}
whispers: dict[str, str] = {}

ANSWERABLE = {"night_choice", "vote", "public_message", "private_partners", "private_message"}
REQUEST_TO_MESSAGE = {"night_choice": "night_request", "vote": "vote_request"}


def register_human(player_id: str, port) -> None:
    """Relie le joueur à son port. Appelée par game_runner, depuis une coroutine."""
    ports[player_id] = port
    asyncio.create_task(_forward_requests(player_id, port))


async def _send_state(player_id: str, port) -> None:
    """Envoie au front l'état de la partie vu par ce joueur. Ignoré tant que la partie n'a pas démarré."""
    if port is None or port.state is None or port.memory is None:
        return
    view = to_front_state(port.state, port.memory, player_id, tuple(port.votes_history))
    await manager.send_to_player(player_id, {"type": "state_update", "data": view})


async def _forward_requests(player_id: str, port) -> None:
    """Lit les demandes du moteur, envoie l'état puis la demande, et retient celle qui attend une réponse."""
    while True:
        request = await port.requests.get()
        kind = request["kind"]
        if kind in ANSWERABLE:
            pending[player_id] = kind
        else:
            pending.pop(player_id, None)
        await _send_state(player_id, port)
        data = {k: v for k, v in request.items() if k != "kind"}
        msg_type = REQUEST_TO_MESSAGE.get(kind, "engine_request")
        await manager.send_to_player(player_id, {"type": msg_type, "kind": kind, "data": data})


def _answer(player_id: str, kind: str, value: Any) -> bool:
    """Donne la réponse au moteur seulement si c'est la demande attendue. Renvoie False sinon."""
    port = ports.get(player_id)
    if port is None or pending.get(player_id) != kind:
        return False
    del pending[player_id]
    port.answers.put_nowait(value)
    return True


@router.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    """
    Endpoint WebSocket principal pour le joueur connecté.
    URL de connexion : ws://<serveur>/ws/player_human_1
    """
    await manager.connect(player_id, websocket)

    # Lance la partie au premier branchement du joueur humain, puis envoie l'état si elle existe.
    # Import local pour éviter le cycle game_runner <-> websockets.
    from backend.server.game_runner import ensure_started
    ensure_started(player_id)
    await _send_state(player_id, ports.get(player_id))

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

                    if channel_id == "public":
                        if _answer(player_id, "public_message", content):
                            await manager.broadcast({
                                "type": "chat",
                                "channel_id": "public",
                                "sender": player_id,
                                "content": content,
                            })
                        else:
                            await manager.send_to_player(
                                player_id,
                                {"type": "error", "data": "Le tchat public n'est pas ouvert en ce moment."}
                            )
                    else:
                        if whispers.get(player_id) == channel_id and _answer(player_id, "private_message", content):
                            await manager.send_to_player(player_id, {
                                "type": "chat",
                                "channel_id": channel_id,
                                "sender": player_id,
                                "content": content,
                            })
                        else:
                            await manager.send_to_player(
                                player_id,
                                {"type": "error", "data": "Ce salon privé n'est pas ouvert ou ce n'est pas le moment d'écrire."}
                            )

                # 2. DEMANDE DE CONVERSATION PRIVÉE
                elif action == "request_whisper":
                    targets = payload.targets
                    logger.info(f"Joueur {player_id} souhaite discuter en privé avec les agents : {targets}")

                    if len(targets) == 0 or len(targets) > 2:
                        await manager.send_to_player(
                            player_id,
                            {"type": "error", "data": "Vous devez sélectionner 1 ou 2 agents maximum pour une discussion privée."}
                        )
                    elif not _answer(player_id, "private_partners", list(targets)):
                        await manager.send_to_player(
                            player_id,
                            {"type": "error", "data": "Ce n'est pas le moment de demander une discussion privée."}
                        )
                    else:
                        participants = sorted([player_id] + targets)
                        channel_id = "whisper_" + "_".join(participants)
                        whispers[player_id] = channel_id

                        # 1. Annonce publique dans le chat pour tout le monde
                        announcement_text = f"💬 {player_id} est entré en discussion privée avec {', '.join(targets)}."
                        await manager.broadcast({
                            "type": "chat",
                            "channel_id": "public",
                            "sender": "Grimoire",
                            "content": announcement_text
                        })

                        # 2. Ouverture effective du canal privé pour l'humain
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
                        # TODO: invitations venant des agents, pas encore branchées au moteur
                    else:
                        pass

                # 4. SOUMISSION DU VOTE
                elif action == "submit_vote":
                    target_id = payload.target_id or None  # "" (personne) devient None

                    if _answer(player_id, "vote", target_id):
                        await manager.send_to_player(
                            player_id,
                            {
                                "type": "announcement",
                                "text": f"Votre vote pour '{target_id or 'personne'}' a bien été pris en compte."
                            }
                        )
                    else:
                        await manager.send_to_player(
                            player_id,
                            {"type": "error", "data": "Ce n'est pas le moment de voter."}
                        )

                # 5. ACTIONS DE NUIT
                elif action == "submit_night_action":
                    targets = payload.targets
                    logger.info(f"Action de nuit reçue de {player_id} avec {len(targets)} cible(s) : {targets}")

                    if len(targets) > 2:
                        await manager.send_to_player(
                            player_id,
                            {"type": "error", "data": "Vous ne pouvez pas cibler plus de 2 joueurs."}
                        )
                    elif _answer(player_id, "night_choice", tuple(targets)):
                        await manager.send_to_player(
                            player_id,
                            {
                                "type": "announcement",
                                "text": "Vos choix nocturnes ont été enregistrés."
                            }
                        )
                    else:
                        await manager.send_to_player(
                            player_id,
                            {"type": "error", "data": "Ce n'est pas le moment d'agir la nuit."}
                        )

                # 6. DÉCLENCHEMENT DU VOTE (SI REFUS DE WHISPER)
                elif action == "trigger_vote_phase":
                    logger.info(f"Le joueur {player_id} a déclenché le passage à la phase de vote.")

                    # Broadcaster à tous les clients connectés le changement de phase
                    await manager.broadcast({
                        "type": "phase_update",
                        "phase": "vote",
                        "announcement": f"Le village (sur l'initiative de {player_id}) passe à la phase de vote."
                    })

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