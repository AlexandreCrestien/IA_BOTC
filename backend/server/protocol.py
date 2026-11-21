"""Ce que le serveur envoie au front (static/js) : traduction des demandes du moteur en messages,
envoi, et tout ce qu'il faut renvoyer après une reconnexion.

Les joueurs sont toujours désignés par leur identifiant (p1…p5, pseudo de l'humain) :
le front affiche leur nom grâce à la liste des joueurs de game_state.
Chaque message est un modèle de backend/server/schemas.py, validé à l'envoi.
Les textes affichés tels quels (consignes, annonces, erreurs) sont écrits ici ; les textes construits
à partir de données (morts de la nuit, résultats des votes, fin de partie) sont écrits par le front.
"""
import logging
from typing import Optional

from backend.models import GameState, Phase
from backend.server.connection_manager import manager
from backend.server.schemas import (
    ActionRequest,
    Announcement,
    AgentWhisperRequest,
    Ally,
    Ballot,
    ChatMessage,
    FrontGameState,
    FrontPlayer,
    GameInterrupted,
    GameOver,
    GameStateMessage,
    History,
    InputRequest,
    NightHistoryEntry,
    NightInfo,
    NightResult,
    OutMessage,
    PrivateChannelOpened,
    RoleAssigned,
    VoteHistoryEntry,
    VoteResult,
)
from backend.server.session import ANSWERABLE, WHISPER_MESSAGES, GameSession

logger = logging.getLogger(__name__)

PUBLIC_CHANNEL = "public"
CODEX = "Codex"  # expéditeur des annonces du chat (pseudo réservé)

# Valeurs attendues par le front (game.js : PHASES, actions.js : kind)
PHASE_FRONT = {
    Phase.NIGHT: "nuit",
    Phase.DISCUSSION: "discussion",
    Phase.VOTE: "vote",
}


def whisper_channel_id(member_ids) -> str:
    """Identifiant d'un salon privé : whisper_<ids triés>."""
    return "whisper_" + "_".join(sorted(member_ids))


def to_front_state(state: GameState) -> FrontGameState:
    """Ce que game.js et players.js affichent : tour, phase, nombre de vivants, joueurs."""
    return FrontGameState(
        day=state.turn,
        phase=PHASE_FRONT[state.phase],
        aliveCount=len(state.alive_players()),
        players=[
            # Mort : le front affiche « vote dispo » ou « vote utilisé »
            FrontPlayer(id=p.id, name=p.name, alive=p.alive, has_vote=p.can_vote)
            for p in state.players
        ],
    )


# --- Envoi ------------------------------------------------------------------------

async def send(player_id: str, message: OutMessage) -> None:
    await manager.send_to_player(player_id, message.model_dump())


async def send_chat(session: GameSession, channel_id: str, sender: str, content: str,
                    broadcast: bool = False) -> None:
    """Envoie un message de chat et le garde pour le renvoyer après une reconnexion.
    broadcast=True : message de la place publique, diffusé à toutes les connexions."""
    message = ChatMessage(channel_id=channel_id, sender=sender, content=content)
    session.chat_log.append(message)
    if broadcast:
        await manager.broadcast(message.model_dump())
    else:
        await send(session.human_id, message)


async def send_state(session: GameSession) -> None:
    """Envoie le rôle (une fois par connexion), puis l'état de la partie.
    Ignoré tant que la partie n'est pas mise en place."""
    if session.state is None:
        return
    if not session.role_sent:
        role = session.state.player(session.human_id).role
        session.role_sent = True
        await send(session.human_id, RoleAssigned(
            role_name=role.name_FR,
            description=role.description,
            allies=session.allies,  # reconnexion d'un joueur du camp du mal après la révélation
        ))
    await send(session.human_id, GameStateMessage(state=to_front_state(session.state)))


async def restore(session: GameSession) -> None:
    """Reconnexion : rouvre les salons privés, renvoie le chat et les historiques Nuits / Votes.
    Le front ne se place sur un salon que si le moteur attend un message privé (demande renvoyée ensuite)."""
    for channel_id, members in session.opened_channels.items():
        await send(session.human_id, PrivateChannelOpened(
            channel_id=channel_id, members=members, text="", focus=False))
    for message in session.chat_log:
        await send(session.human_id, message)
    if session.night_log or session.vote_log:
        await send(session.human_id, History(nights=session.night_log, votes=session.vote_log))


async def open_whisper(session: GameSession, partner_ids: list[str]) -> None:
    """Ouvre le salon privé du joueur avec ses interlocuteurs, annoncé sur la place publique.
    Le salon est enregistré avant tout envoi : les réponses des agents le trouvent."""
    human = session.human_id
    channel_id = whisper_channel_id([human] + partner_ids)
    session.whisper = channel_id
    session.whisper_left = WHISPER_MESSAGES
    members = sorted([human] + partner_ids)
    session.opened_channels[channel_id] = members

    names = ", ".join(session.state.player(pid).name for pid in partner_ids)
    me = session.state.player(human).name
    await send_chat(session, PUBLIC_CHANNEL, CODEX,
                    f"💬 {me} est entré en discussion privée avec {names}.", broadcast=True)
    await send(human, PrivateChannelOpened(channel_id=channel_id, members=members,
                                           text=f"Salon privé ouvert avec {names}"))


async def send_game_interrupted(player_id: str) -> None:
    """La partie a planté : le front propose d'en relancer une."""
    await send(player_id, GameInterrupted(text="Une erreur a interrompu la partie. Vous pouvez en lancer une nouvelle."))


# --- Demandes du moteur -----------------------------------------------------------

async def forward_requests(session: GameSession) -> None:
    """Relais : lit les demandes du moteur, envoie l'état puis la demande, et retient celle qui attend une réponse."""
    while True:
        request = await session.port.requests.get()
        session.state = request["state"]
        session.pending = request if request["kind"] in ANSWERABLE else None
        await send_state(session)
        await send_request(session, request)


async def send_request(session: GameSession, request: dict) -> None:
    """Traduit une demande du moteur en message pour le front."""
    human, state, kind = session.human_id, request["state"], request["kind"]

    if kind == "night_choice":
        await send(human, ActionRequest(
            kind="nuit", candidates=request["targets"],
            max_targets=request["count"], min_targets=request["count"],
            role=state.player(human).role.name_EN,
        ))

    elif kind == "vote":
        await send(human, ActionRequest(kind="vote", candidates=request["targets"]))

    elif kind == "private_partners":
        await send(human, ActionRequest(kind="discussion", candidates=request["choices"],
                                        max_targets=2, min_targets=1))

    elif kind == "agent_invitation":
        # Le joueur n'a choisi personne à temps : un agent lui propose un entretien (modale)
        await send(human, AgentWhisperRequest(agent_id=request["agent"]))

    # Saisie attendue (facultative) : le front affiche un bandeau au-dessus du chat, avec « Passer »
    elif kind == "public_message":
        await send(human, InputRequest(kind="public_message", channel_id=PUBLIC_CHANNEL,
                                       text="C'est à vous de parler sur la place publique."))

    elif kind == "private_message":
        left = session.whisper_left
        await send(human, InputRequest(
            kind="private_message", channel_id=session.whisper, left=left,
            text=f"Il vous reste {left} message(s) privé(s) avec vos interlocuteurs.",
        ))

    elif kind == "public_chat":
        # Message public d'un agent IA, pendant la discussion du jour
        await send_chat(session, PUBLIC_CHANNEL, request["author"], request["text"])

    elif kind == "agent_meeting":
        # Deux agents s'entretiennent en privé pendant le salon du joueur : annonce publique
        first, second = (state.player(pid).name for pid in request["agents"])
        await send_chat(session, PUBLIC_CHANNEL, CODEX,
                        f"💬 {first} et {second} se sont entretenus en privé.", broadcast=True)

    elif kind == "valet_blocked":
        # Le joueur est le Valet et son maître n'a pas voté : information privée (il connaît son rôle)
        master = state.player(request["master"]).name
        await send(human, Announcement(
            text=f"Votre maître, {master}, n'a pas voté : en tant que Valet, vous ne pouvez pas voter aujourd'hui."))

    elif kind == "agent_unavailable":
        await report_agent_unavailable(session, state, request["agent"], request["step"])

    elif kind == "night_info":
        # Information privée de nuit (première nuit, Médium). allies seulement pour le camp du mal.
        allies = [Ally(**ally) for ally in request["allies"]] if request["allies"] is not None else None
        if allies is not None:
            session.allies = allies
        session.night_log.append(NightHistoryEntry(turn=request["turn"], type="role_info", info=request["info"]))
        await send(human, NightInfo(turn=request["turn"], info=request["info"], allies=allies))

    elif kind == "night_deaths":
        # Le front n'affiche qu'un mort par nuit : on envoie le premier.
        deaths = request["deaths"]
        dead = deaths[0] if deaths else None
        session.night_log.append(NightHistoryEntry(turn=state.turn, type="result", dead_player=dead))
        await send(human, NightResult(turn=state.turn, dead_player=dead))

    elif kind == "private_replies":
        if session.whisper is None:
            logger.warning("Réponses privées sans salon ouvert pour %s", human)
            return
        for reply in request["replies"]:
            await send_chat(session, session.whisper, reply["author"], reply["text"])

    # Fin de tour et fin de partie (posées dans la file par game_runner, pour garder l'ordre)
    elif kind == "vote_result":
        await send_vote_result(session, request["turn"], request["executed"], request["votes"])

    elif kind == "game_over":
        await send(human, GameOver(winner=request["winner"], details=request["details"]))

    else:
        logger.info("Demande du moteur sans équivalent front : %s", kind)


async def send_vote_result(session: GameSession, turn: int, executed: Optional[str], votes: list[dict]) -> None:
    """votes : [{"voter": id, "target": id ou None, "ghost": bool, "unavailable": bool}]. Gardés pour l'onglet Votes."""
    ballots = [Ballot(**vote) for vote in votes]
    session.vote_log.extend(
        VoteHistoryEntry(turn=turn, voter=b.voter, target=b.target, executed=executed, unavailable=b.unavailable)
        for b in ballots)
    await send(session.human_id, VoteResult(turn=turn, executed=executed, votes=ballots))


# Échecs d'un agent IA (son modèle n'a pas répondu) : ce que le joueur voit selon le moment
FAILURE_BANNER_AFTER = 3  # échecs dans la partie avant le bandeau « les IA rencontrent des difficultés »


async def report_agent_unavailable(session: GameSession, state: GameState, agent_id: str, step: str) -> None:
    """Discussion : message du Codex sur la place publique. Salon privé : message du Codex dans le salon.
    Vote : rien ici, le bulletin porte la mention « IA indisponible ». Nuit : rien, ce serait révéler
    que l'agent a un pouvoir de nuit. Tout est gardé pour le panel admin ; bandeau une seule fois si
    les échecs s'accumulent (panne d'un fournisseur)."""
    name = state.player(agent_id).name
    session.agent_failures.append({"turn": state.turn, "phase": state.phase.value, "agent": agent_id, "step": step})
    if step == "public":
        await send_chat(session, PUBLIC_CHANNEL, CODEX, f"🕯️ {name} ne dit rien : son IA n'a pas répondu.",
                        broadcast=True)
    elif step == "private" and session.whisper is not None:
        await send_chat(session, session.whisper, CODEX, f"🕯️ {name} ne répond pas : son IA n'a pas répondu.")
    if len(session.agent_failures) >= FAILURE_BANNER_AFTER and not session.failure_banner_shown:
        session.failure_banner_shown = True
        await send(session.human_id, Announcement(
            text="Les IA rencontrent des difficultés : la partie continue avec des réponses de secours."))
