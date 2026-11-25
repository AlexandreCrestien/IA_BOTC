"""Endpoint WebSocket du joueur humain : connexion, reprise après coupure, et actions reçues du front.
Ce que le serveur envoie au front est dans protocol.py ; la partie en cours dans session.py."""
import json
import logging
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, TypeAdapter, ValidationError

from backend.accounts.service import user_from_token
from backend.accounts.tokens import COOKIE_NAME
from backend.db import User, get_session
from backend.server import game_runner
from backend.server.connection_manager import manager
from backend.server.protocol import (
    PUBLIC_CHANNEL,
    open_whisper,
    restore,
    send,
    send_chat,
    send_request,
    send_state,
)
from backend.server.schemas import (
    Announcement,
    ClientActionPacket,
    Connected,
    Error,
    GameAbandoned,
    GuestSession,
    NightActionAck,
    ReportResult,
)
from backend.server.reports import save_report
from backend.server.session import WHISPER_MESSAGES, GameSession, current_session

logger = logging.getLogger(__name__)

router = APIRouter()

action_validator = TypeAdapter(ClientActionPacket)

# Étapes facultatives que le joueur peut passer, et la réponse « rien » attendue par le moteur
SKIPPABLE = {"public_message": None, "private_message": None, "private_partners": []}

# Code de fermeture WebSocket quand la connexion est refusée (le front affiche le motif sur l'accueil)
CLOSE_REFUSED = 4001


async def _error(session: GameSession, text: str) -> None:
    await send(session.human_id, Error(data=text))


def check_answer(session: GameSession, kind: str, value) -> str | None:
    """Message d'erreur si la réponse ne respecte pas la demande en cours, sinon None.
    Si la demande attendue n'est pas celle-ci, renvoie None : session.answer refusera la réponse."""
    if not session.waits_for(kind):
        return None
    request = session.pending

    if kind == "night_choice":
        if len(value) != request["count"] or len(set(value)) != len(value):
            return f"Il faut choisir exactement {request['count']} joueur(s), sans doublon."
        allowed = request["targets"]

    elif kind == "private_partners":
        if not 1 <= len(value) <= 2 or len(set(value)) != len(value) or session.human_id in value:
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


# --- Actions du joueur (une fonction par action, payload validé par schemas.py) -------------

async def on_send_chat(session: GameSession, payload) -> None:
    """Message sur la place publique ou dans le salon privé, seulement quand le moteur l'attend."""
    channel_id, content, me = payload.channel_id, payload.content, session.human_id

    if channel_id == PUBLIC_CHANNEL:
        if session.answer("public_message", content):
            await send_chat(session, PUBLIC_CHANNEL, me, content, broadcast=True)
        else:
            await _error(session, "Le tchat public n'est pas ouvert en ce moment.")
        return

    closed = "Ce salon privé n'est pas ouvert ou ce n'est pas le moment d'écrire."
    if session.whisper != channel_id or not session.waits_for("private_message"):
        await _error(session, closed)
    elif session.whisper_left <= 0:
        await _error(session, f"Vous avez déjà utilisé vos {WHISPER_MESSAGES} messages privés.")
    elif session.answer("private_message", content):
        session.whisper_left -= 1
        await send_chat(session, channel_id, me, content)
    else:
        await _error(session, closed)


async def on_request_whisper(session: GameSession, payload) -> None:
    """Le joueur choisit 1 ou 2 interlocuteurs pour son salon privé."""
    targets = list(payload.targets)
    error = check_answer(session, "private_partners", targets)
    if error:
        await _error(session, error)
    elif not session.answer("private_partners", targets):
        await _error(session, "Ce n'est pas le moment de demander une discussion privée.")
    else:
        await open_whisper(session, targets)


async def on_discussion_timeout(session: GameSession, payload) -> None:
    """Aucun choix de salon privé à temps : un agent va proposer un entretien."""
    if not session.answer("private_partners", None):
        await _error(session, "Ce n'est pas le moment de choisir une discussion privée.")


async def on_respond_whisper_invitation(session: GameSession, payload) -> None:
    """Réponse à la proposition d'entretien d'un agent (refus : place au vote)."""
    agent_id = session.pending["agent"] if session.waits_for("agent_invitation") else None
    if agent_id is None or payload.target_agent_id != agent_id:
        await _error(session, "Aucune proposition d'entretien en attente.")
    elif session.answer("agent_invitation", payload.accepted):
        if payload.accepted:
            await open_whisper(session, [agent_id])
        else:
            await send(session.human_id, Announcement(text="Entretien refusé : place au vote."))


async def on_submit_vote(session: GameSession, payload) -> None:
    """Vote (target_id vide ou null : « Personne »)."""
    target = payload.target_id or None
    error = check_answer(session, "vote", target)
    if error:
        await _error(session, error)
    elif session.answer("vote", target):
        shown = session.state.player(target).name if target else "Personne"
        await send(session.human_id, Announcement(text=f"Votre vote pour {shown} a bien été pris en compte."))
    else:
        await _error(session, "Ce n'est pas le moment de voter.")


async def on_submit_night_action(session: GameSession, payload) -> None:
    targets = list(payload.targets)
    error = check_answer(session, "night_choice", targets)
    if error:
        await _error(session, error)
    elif session.answer("night_choice", tuple(targets)):
        await send(session.human_id, NightActionAck(text="Le Maître du Jeu a bien reçu votre choix."))
    else:
        await _error(session, "Ce n'est pas le moment d'agir la nuit.")


async def on_skip_turn(session: GameSession, payload) -> None:
    """Passer une étape facultative : message public, salon privé, fin du salon."""
    if not session.answer(payload.kind, SKIPPABLE[payload.kind]):
        await _error(session, "Il n'y a rien à passer en ce moment.")
    elif payload.kind == "private_partners":
        await send(session.human_id, Announcement(text="Pas de discussion privée : place au vote."))


async def on_abandon_game(session: GameSession, payload) -> None:
    """Abandon : le front recharge la page et revient à l'accueil."""
    if game_runner.abandon_game(session.human_id):
        await send(session.human_id, GameAbandoned())
    else:
        await _error(session, "Aucune partie en cours à abandonner.")


async def on_report_message(session: GameSession, payload) -> None:
    """Signalement d'un message d'agent IA (joueur connecté), possible aussi sur l'écran de fin."""
    error = save_report(session, payload.message_id, payload.category, payload.comment)
    await send(session.human_id, ReportResult(message_id=payload.message_id, error=error))


ACTIONS: dict[str, Callable[[GameSession, BaseModel], Awaitable[None]]] = {
    "send_chat": on_send_chat,
    "request_whisper": on_request_whisper,
    "discussion_timeout": on_discussion_timeout,
    "respond_whisper_invitation": on_respond_whisper_invitation,
    "submit_vote": on_submit_vote,
    "submit_night_action": on_submit_night_action,
    "skip_turn": on_skip_turn,
    "abandon_game": on_abandon_game,
    "report_message": on_report_message,
}


# --- Connexion --------------------------------------------------------------------------

def _connected_user(websocket: WebSocket) -> Optional[User]:
    """Compte du joueur, d'après le cookie de connexion envoyé à l'ouverture du WebSocket (None : invité)."""
    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with get_session() as db:
        return user_from_token(db, token)


async def _resume(session: GameSession) -> None:
    """Nouvelle connexion : rôle et état, chat, salons et historiques, puis la demande en attente.
    Invité : jeton qui permet de rattacher la partie à un compte s'il s'inscrit."""
    if session.guest_token is not None:
        await send(session.human_id, GuestSession(guest_token=session.guest_token))
    session.role_sent = False  # le front repart d'une page vide
    await send_state(session)
    await restore(session)
    if session.pending is not None:
        await send_request(session, session.pending)


async def _handle(player_id: str, raw_data: str) -> None:
    """Valide une action reçue et la confie à son traitement."""
    try:
        packet = action_validator.validate_python(json.loads(raw_data))
    except json.JSONDecodeError:
        logger.warning("Message JSON invalide reçu de %s", player_id)
        await manager.send_to_player(player_id, Error(data="Format JSON invalide.").model_dump())
        return
    except ValidationError as e:
        logger.warning("Action non valide reçue de %s : %s", player_id, e.errors())
        await manager.send_to_player(player_id, Error(data=f"Action non valide : {e.errors()}").model_dump())
        return

    logger.info("Action reçue de %s -> %s | %s", player_id, packet.action, packet.payload)
    session = current_session()
    if session is None or session.human_id != player_id:
        await manager.send_to_player(player_id, Error(data="Aucune partie en cours.").model_dump())
        return
    await ACTIONS[packet.action](session, packet.payload)


@router.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    """Endpoint WebSocket du joueur. URL de connexion : ws://<serveur>/ws/<pseudo>"""
    # Refus (pseudo invalide, partie d'un autre joueur) : on accepte avant de refermer,
    # sinon le navigateur ne peut pas lire le motif du refus.
    user = _connected_user(websocket)
    refusal = game_runner.can_join(player_id, user)
    if refusal is not None:
        await websocket.accept()
        await websocket.close(code=CLOSE_REFUSED, reason=refusal)
        logger.info("Connexion refusée pour %s : %s", player_id, refusal)
        return

    # Le joueur voit l'écran de jeu tout de suite, avant la mise en place de la partie (quelques secondes)
    await manager.connect(player_id, websocket)
    await manager.send_to_player(player_id, Connected().model_dump())

    # Nouvelle partie, ou reprise de la partie en cours
    refusal = game_runner.ensure_started(player_id, user)
    if refusal is not None:  # cas limite : un autre joueur a lancé une partie entre-temps
        await websocket.close(code=CLOSE_REFUSED, reason=refusal)
        manager.disconnect(player_id, websocket)
        return
    session = current_session()
    if session is not None and session.human_id == player_id:
        await _resume(session)

    try:
        while True:
            await _handle(player_id, await websocket.receive_text())
    except WebSocketDisconnect:
        manager.disconnect(player_id, websocket)
        logger.info("Déconnexion de %s ; la partie attend sa reconnexion.", player_id)
