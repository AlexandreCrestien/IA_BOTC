import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from backend.front_state import to_front_state, whisper_channel_id
from backend.server.connection_manager import manager
from backend.server.schemas import ClientActionPacket

logger = logging.getLogger(__name__)

router = APIRouter()

action_validator = TypeAdapter(ClientActionPacket)

# Par joueur humain : port du moteur, demande en attente de réponse (kind), dernière demande
# à réafficher en cas de reconnexion, salon privé ouvert, messages privés restants,
# et rôles déjà envoyés au front (renvoyés à chaque connexion).
ports: dict[str, Any] = {}
pending: dict[str, str] = {}
current_request: dict[str, tuple[str, dict]] = {}
whispers: dict[str, str] = {}
whisper_left: dict[str, int] = {}
roles_sent: set[str] = set()
forward_tasks: dict[str, asyncio.Task] = {}  # relais des demandes du moteur, par joueur

# Demandes du moteur auxquelles le joueur doit répondre
ANSWERABLE = {"night_choice", "vote", "public_message", "private_partners", "private_message"}
PUBLIC_CHANNEL = "public"
WHISPER_MESSAGES = 3  # messages privés autorisés par salon

# Code de fermeture WebSocket quand la connexion est refusée (le front affiche le motif sur l'accueil)
CLOSE_REFUSED = 4001


def register_human(player_id: str, port) -> None:
    """Relie le joueur à son port. Appelée par game_runner, depuis une coroutine."""
    reset_player(player_id)
    ports[player_id] = port
    forward_tasks[player_id] = asyncio.create_task(_forward_requests(player_id, port))


def reset_player(player_id: str) -> None:
    """Efface tout ce que le serveur retient de la partie de ce joueur (fin de partie, abandon)."""
    task = forward_tasks.pop(player_id, None)
    if task is not None:
        task.cancel()
    for store in (ports, pending, current_request, whispers, whisper_left):
        store.pop(player_id, None)
    roles_sent.discard(player_id)


async def _send(player_id: str, message: dict) -> None:
    await manager.send_to_player(player_id, message)


def _human_role(port, player_id: str):
    return port.state.player(player_id).role


# Noms affichés : le front ne voit jamais les identifiants internes (p1, p2...)
def _all_players(state):
    players = state.players
    return players.values() if isinstance(players, dict) else players


def _name(port, player_id: str) -> str:
    """Nom affiché pour un identifiant. Repli : l'identifiant lui-même."""
    if port is None or port.state is None:
        return player_id
    try:
        return port.state.player(player_id).name
    except Exception:
        return player_id


def _names(port, player_ids) -> list[str]:
    return [_name(port, p) for p in player_ids]


def _id_from_name(port, value):
    """Nom choisi dans le front -> identifiant du moteur. Renvoie value si aucun joueur ne correspond."""
    if port is None or port.state is None or value is None:
        return value
    wanted = str(value).casefold()
    for player in _all_players(port.state):
        if player.name.casefold() == wanted:
            return player.id
    return value


def _current_request(player_id: str) -> dict | None:
    entry = current_request.get(player_id)
    return entry[1] if entry else None


async def _send_state(player_id: str, port) -> None:
    """Envoie le rôle (à chaque connexion), puis l'état de la partie. Ignoré tant que la partie n'a pas démarré."""
    if port is None or port.state is None:
        return
    if player_id not in roles_sent:
        role = _human_role(port, player_id)
        roles_sent.add(player_id)
        await _send(player_id, {
            "type": "role_assigned",
            "role_name": role.name_FR,
            "description": getattr(role, "description", ""),
        })
    await _send(player_id, {"type": "game_state", "state": to_front_state(port.state)})


async def _forward_requests(player_id: str, port) -> None:
    """Lit les demandes du moteur, envoie l'état puis la demande, et retient celle qui attend une réponse."""
    while True:
        request = await port.requests.get()
        kind = request["kind"]
        if kind in ANSWERABLE:
            pending[player_id] = kind
            current_request[player_id] = (kind, request)
        else:
            pending.pop(player_id, None)
        await _send_state(player_id, port)
        await _send_request(player_id, port, kind, request)


async def _send_request(player_id: str, port, kind: str, request: dict) -> None:
    """Traduit une demande du moteur en message compris par le front, avec des noms."""
    if kind == "night_choice":
        await _send(player_id, {
            "type": "action_request",
            "kind": "nuit",
            "candidates": _names(port, request["targets"]),
            "max_targets": request["count"],
            "min_targets": request["count"],
            "role": _human_role(port, player_id).name_EN,
        })

    elif kind == "vote":
        await _send(player_id, {
            "type": "action_request",
            "kind": "vote",
            "candidates": _names(port, request["targets"]),
        })

    elif kind == "private_partners":
        await _send(player_id, {
            "type": "action_request",
            "kind": "discussion",
            "candidates": _names(port, request["choices"]),
            "max_targets": 2,
            "min_targets": 1,
        })

    elif kind == "public_message":
        await _send(player_id, {
            "type": "announcement",
            "text": "Le village attend votre message public pour passer au vote.",
        })

    elif kind == "private_message":
        left = whisper_left.get(player_id, WHISPER_MESSAGES)
        await _send(player_id, {
            "type": "announcement",
            "text": f"Il vous reste {left} message(s) privé(s) avec vos interlocuteurs.",
        })

    elif kind == "public_chat":
        # Message public d'un agent IA, pendant la discussion du jour
        await _send(player_id, {
            "type": "chat",
            "channel_id": PUBLIC_CHANNEL,
            "sender": _name(port, request["author"]),
            "content": request["text"],
        })

    elif kind == "night_info":
        # Information privée de nuit (première nuit, Voyante). allies seulement pour le camp du mal.
        message = {"type": "night_info", "turn": request["turn"], "info": request["info"]}
        if request["allies"] is not None:
            message["allies"] = request["allies"]
        await _send(player_id, message)

    elif kind == "night_deaths":
        # Le front n'affiche qu'un mort par nuit : on envoie le premier, par son nom.
        deaths = request.get("deaths") or []
        await _send(player_id, {
            "type": "night_result",
            "turn": port.state.turn,
            "dead_player": _name(port, deaths[0]) if deaths else None,
        })

    elif kind == "private_replies":
        channel_id = whispers.get(player_id)
        if channel_id is None:
            logger.warning(f"Réponses privées sans salon ouvert pour {player_id}")
            return
        for reply in request.get("replies", []):
            await _send(player_id, {
                "type": "chat",
                "channel_id": channel_id,
                "sender": _name(port, reply["author"]),
                "content": reply["text"],
            })

    else:
        logger.info(f"Demande du moteur sans équivalent front : {kind}")


def _check_answer(player_id: str, kind: str, value) -> str | None:
    """Message d'erreur si la réponse ne respecte pas la demande en cours, sinon None.
    Si la demande attendue n'est pas celle-ci, renvoie None : _answer refusera la réponse."""
    request = _current_request(player_id)
    if request is None or pending.get(player_id) != kind:
        return None

    if kind == "night_choice":
        if len(value) != request["count"] or len(set(value)) != len(value):
            return f"Il faut choisir exactement {request['count']} joueur(s), sans doublon."
        allowed = request["targets"]

    elif kind == "private_partners":
        if not 1 <= len(value) <= 2 or len(set(value)) != len(value) or player_id in value:
            return "Choisissez 1 ou 2 interlocuteurs, sans vous-même."
        allowed = request["choices"]

    elif kind == "vote":
        if value is None:  # « Personne » : toujours permis
            return None
        allowed = request["targets"]
        value = [value]

    else:
        return None

    if any(v not in allowed for v in value):
        return "Choix non valide : ce joueur ne peut pas être choisi maintenant."
    return None


def _answer(player_id: str, kind: str, value: Any) -> bool:
    """Donne la réponse au moteur seulement si c'est la demande attendue. Renvoie False sinon."""
    port = ports.get(player_id)
    if port is None or pending.get(player_id) != kind:
        return False
    del pending[player_id]
    current_request.pop(player_id, None)
    port.answers.put_nowait(value)
    return True


# Messages de fin de vote / de fin de partie : appelés par game_runner (noms, pas identifiants)
async def send_vote_result(player_id: str, turn: int, executed: str | None, votes: list[dict]) -> None:
    """votes : [{"voter": nom, "target": nom ou None}]. executed : nom ou None."""
    await _send(player_id, {"type": "vote_result", "turn": turn, "executed": executed, "votes": votes})


async def send_game_over(player_id: str, winner: str, details: str) -> None:
    await _send(player_id, {"type": "game_over", "winner": winner, "details": details})


async def send_game_interrupted(player_id: str) -> None:
    """La partie a planté : le front propose d'en relancer une."""
    await _send(player_id, {
        "type": "game_interrupted",
        "text": "Une erreur a interrompu la partie. Vous pouvez en lancer une nouvelle.",
    })


@router.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    """
    Endpoint WebSocket principal pour le joueur connecté.
    URL de connexion : ws://<serveur>/ws/<pseudo>
    """
    # Import local pour éviter le cycle game_runner <-> websockets
    from backend.server.game_runner import abandon_game, can_join, ensure_started

    # Refus (pseudo invalide, partie d'un autre joueur) : on accepte avant de refermer,
    # sinon le navigateur ne peut pas lire le motif du refus.
    refusal = can_join(player_id)
    if refusal is not None:
        await websocket.accept()
        await websocket.close(code=CLOSE_REFUSED, reason=refusal)
        logger.info(f"Connexion refusée pour {player_id} : {refusal}")
        return

    # Le joueur voit l'écran de jeu tout de suite, avant la mise en place de la partie (quelques secondes)
    await manager.connect(player_id, websocket)
    await _send(player_id, {"type": "connected"})

    # Nouvelle partie, ou reprise de la partie en cours
    refusal = ensure_started(player_id)
    if refusal is not None:  # cas limite : un autre joueur a lancé une partie entre-temps
        await websocket.close(code=CLOSE_REFUSED, reason=refusal)
        manager.disconnect(player_id, websocket)
        return
    port = ports.get(player_id)
    await _send_state(player_id, port)

    # Reprise après coupure : si le moteur attendait une réponse, on la redemande
    if player_id in current_request:
        kind, request = current_request[player_id]
        await _send_request(player_id, port, kind, request)

    try:
        while True:
            raw_data = await websocket.receive_text()

            try:
                action_packet = action_validator.validate_python(json.loads(raw_data))
                action = action_packet.action
                payload = action_packet.payload
                port = ports.get(player_id)

                logger.info(f"Action reçue de {player_id} -> Type: {action} | Payload: {payload}")

                # 1. CHAT (place publique ou salon privé)
                if action == "send_chat":
                    channel_id = payload.channel_id
                    content = payload.content
                    sender = _name(port, player_id)

                    if channel_id == PUBLIC_CHANNEL:
                        if _answer(player_id, "public_message", content):
                            await manager.broadcast({
                                "type": "chat",
                                "channel_id": PUBLIC_CHANNEL,
                                "sender": sender,
                                "content": content,
                            })
                        else:
                            await _send(player_id, {"type": "error", "data": "Le tchat public n'est pas ouvert en ce moment."})
                    else:
                        left = whisper_left.get(player_id, WHISPER_MESSAGES)
                        if whispers.get(player_id) != channel_id or pending.get(player_id) != "private_message":
                            await _send(player_id, {"type": "error", "data": "Ce salon privé n'est pas ouvert ou ce n'est pas le moment d'écrire."})
                        elif left <= 0:
                            await _send(player_id, {"type": "error", "data": f"Vous avez déjà utilisé vos {WHISPER_MESSAGES} messages privés."})
                        elif _answer(player_id, "private_message", content):
                            whisper_left[player_id] = left - 1
                            await _send(player_id, {
                                "type": "chat",
                                "channel_id": channel_id,
                                "sender": sender,
                                "content": content,
                            })
                        else:
                            await _send(player_id, {"type": "error", "data": "Ce salon privé n'est pas ouvert ou ce n'est pas le moment d'écrire."})

                # 2. DEMANDE DE CONVERSATION PRIVÉE (les noms choisis sont convertis en identifiants)
                elif action == "request_whisper":
                    targets = [_id_from_name(port, t) for t in payload.targets]
                    error = _check_answer(player_id, "private_partners", targets)

                    if error:
                        await _send(player_id, {"type": "error", "data": error})
                    elif not _answer(player_id, "private_partners", targets):
                        await _send(player_id, {"type": "error", "data": "Ce n'est pas le moment de demander une discussion privée."})
                    else:
                        channel_id = whisper_channel_id([player_id] + targets)
                        whispers[player_id] = channel_id
                        whisper_left[player_id] = WHISPER_MESSAGES
                        partners = ", ".join(_names(port, targets))

                        await manager.broadcast({
                            "type": "chat",
                            "channel_id": PUBLIC_CHANNEL,
                            "sender": "Grimoire",
                            "content": f"💬 {_name(port, player_id)} est entré en discussion privée avec {partners}.",
                        })
                        await _send(player_id, {
                            "type": "private_channel_opened",
                            "channel_id": channel_id,
                            "members": sorted(_names(port, [player_id] + targets)),
                            "text": f"Salon privé ouvert avec {partners}",
                        })

                # 3. RÉPONSE À UNE INVITATION D'UN AGENT
                elif action == "respond_whisper_invitation":
                    # TODO: invitations venant des agents, pas encore branchées au moteur
                    if payload.accepted:
                        await _send(player_id, {
                            "type": "announcement",
                            "text": f"Canal privé ouvert avec {payload.target_agent_id}.",
                        })

                # 4. VOTE (target_id = null pour « Personne »)
                elif action == "submit_vote":
                    target = _id_from_name(port, payload.target_id or None)  # "" ou null : « Personne »
                    error = _check_answer(player_id, "vote", target)

                    if error:
                        await _send(player_id, {"type": "error", "data": error})
                    elif _answer(player_id, "vote", target):
                        shown = _name(port, target) if target else "Personne"
                        await _send(player_id, {
                            "type": "announcement",
                            "text": f"Votre vote pour {shown} a bien été pris en compte.",
                        })
                    else:
                        await _send(player_id, {"type": "error", "data": "Ce n'est pas le moment de voter."})

                # 5. ACTION DE NUIT (noms convertis en identifiants)
                elif action == "submit_night_action":
                    targets = [_id_from_name(port, t) for t in payload.targets]
                    error = _check_answer(player_id, "night_choice", targets)

                    if error:
                        await _send(player_id, {"type": "error", "data": error})
                    elif _answer(player_id, "night_choice", tuple(targets)):
                        await _send(player_id, {
                            "type": "night_action_ack",
                            "text": "Le Maître du Jeu a bien reçu votre choix.",
                        })
                    else:
                        await _send(player_id, {"type": "error", "data": "Ce n'est pas le moment d'agir la nuit."})

                # 6. PASSAGE AU VOTE (pas encore branché au moteur)
                elif action == "trigger_vote_phase":
                    await manager.broadcast({
                        "type": "phase_update",
                        "phase": "vote",
                        "announcement": f"Le village (sur l'initiative de {_name(port, player_id)}) passe à la phase de vote.",
                    })

                # 7. ABANDON : le front recharge la page et revient à l'accueil
                elif action == "abandon_game":
                    if abandon_game(player_id):
                        await _send(player_id, {"type": "game_abandoned"})
                    else:
                        await _send(player_id, {"type": "error", "data": "Aucune partie en cours à abandonner."})

                else:
                    logger.warning(f"Action non reconnue reçue de {player_id}: {action}")

            except json.JSONDecodeError:
                logger.warning(f"Message JSON invalide reçu de {player_id}")
                await _send(player_id, {"type": "error", "data": "Format JSON invalide."})

            except ValidationError as e:
                logger.warning(f"Erreur de validation de l'action pour {player_id}: {e.errors()}")
                await _send(player_id, {"type": "error", "data": f"Action non valide : {e.errors()}"})

    except WebSocketDisconnect:
        manager.disconnect(player_id, websocket)
        # Le rôle sera renvoyé à la prochaine connexion (le front repart d'une page vide)
        roles_sent.discard(player_id)
        logger.info(f"Déconnexion de la WebSocket pour le joueur : {player_id} ; la partie attend sa reconnexion.")