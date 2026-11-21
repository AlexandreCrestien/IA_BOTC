"""Lance la partie dans le même processus que le serveur, à la première connexion du joueur humain.
Une seule partie à la fois : la session courante (backend/server/session.py)."""
import asyncio
import logging
import random
from typing import Optional

from backend.game_config import AI_NAMES, PERSONALITY_NAMES
from backend.game_engine import setup_game
from backend.models import Alignement
from backend.server.protocol import GRIMOIRE, forward_requests, send_game_interrupted
from backend.server.session import GameSession, current_session, set_current_session
from backend.turns import play_turn

logger = logging.getLogger(__name__)

# Configuration de la partie. Le joueur humain prend le pseudo qu'il choisit à la connexion.
GAME_CONFIG = {
    "personality_names": PERSONALITY_NAMES,
    "seed": None,  # tests : fixer une graine pour rejouer la même partie
}

# Camp vainqueur, tel qu'envoyé au front (qui écrit le titre et compare au camp du joueur)
WINNER_TEAMS = {Alignement.BON: "good", Alignement.MAUVAIS: "evil"}

# Motifs de refus envoyés au front (affichés sur l'écran d'accueil)
REFUSED_PSEUDO = "Ce pseudo est réservé ou invalide : choisissez-en un autre."
REFUSED_BUSY = "Une partie est déjà en cours avec un autre joueur."


def ballots(state, votes: dict[str, Optional[str]], executed: Optional[str]) -> list[dict]:
    """Bulletins du tour pour le front. state = état en fin de tour.
    Vote fantôme : votant déjà mort au moment du vote. On meurt la nuit (avant le vote) ou par
    exécution (après) : mort en fin de tour sans avoir été exécuté = déjà mort au moment du vote."""
    dead = {p.id for p in state.players if not p.alive}
    return [
        {"voter": voter, "target": target, "ghost": voter in dead and voter != executed}
        for voter, target in votes.items()
    ]


async def run_game(session: GameSession, names: dict[str, str], personality_names: list[str], seed=None):
    rng = random.Random(seed)
    state, agents, memory = setup_game(names, session.human_id, personality_names, rng)
    session.state, session.memory, session.agents = state, memory, agents
    port = session.port

    while True:
        turn = state.turn
        result = await play_turn(state, rng, agents, memory, session.human_id, port)
        state = result.state
        # Même file que les messages du moteur : le front reçoit tout dans l'ordre
        # (sinon la fin de partie pourrait arriver avant les morts de la dernière nuit).
        await port.show_turn_result(state, turn, ballots(state, result.votes, result.executed), result.executed)

        if result.game_winner is not None:
            logger.info("Partie terminée, vainqueur : %s", result.game_winner)
            await port.show_game_over(state, WINNER_TEAMS[result.game_winner],
                                      "Le village a rendu son dernier verdict.")
            return state


def _on_game_end(session: GameSession, task: asyncio.Task) -> None:
    """Fin de la tâche de partie. Si elle a planté, le joueur est prévenu (sinon son écran resterait figé)."""
    if task.cancelled():
        return  # abandon : le joueur a déjà été prévenu
    error = task.exception()
    if error is not None:
        logger.error("Partie interrompue", exc_info=error)
        asyncio.ensure_future(send_game_interrupted(session.human_id))


def start_game(human_id: str, names: dict[str, str], personality_names: list[str], seed=None) -> GameSession:
    """Crée la session et lance la partie, avec le relais de ses demandes vers le front.
    Doit être appelée depuis une coroutine."""
    session = GameSession(human_id=human_id)
    set_current_session(session)
    session.forward_task = asyncio.create_task(forward_requests(session))
    session.game_task = asyncio.create_task(run_game(session, names, personality_names, seed))
    session.game_task.add_done_callback(lambda task: _on_game_end(session, task))
    return session


def _game_running() -> bool:
    session = current_session()
    return session is not None and session.running


def _pseudo_is_valid(pseudo: str) -> bool:
    """Refuse un pseudo vide, réservé, ou déjà pris par un agent (sans tenir compte de la casse)."""
    taken = {k.casefold() for k in AI_NAMES} | {v.casefold() for v in AI_NAMES.values()}
    taken |= {"game_master", GRIMOIRE.casefold()}
    return pseudo.strip() != "" and pseudo.casefold() not in taken


def can_join(player_id: str) -> Optional[str]:
    """Le joueur peut-il entrer ? None si oui, sinon le motif du refus. Ne lance rien."""
    if not _pseudo_is_valid(player_id):
        return REFUSED_PSEUDO
    if _game_running() and player_id != current_session().human_id:
        return REFUSED_BUSY
    return None


def ensure_started(player_id: str) -> Optional[str]:
    """Appelée à chaque connexion. Renvoie None si le joueur peut jouer, sinon le motif du refus.

    - partie en cours avec ce pseudo : reprise (le serveur renvoie l'état et la demande en attente) ;
    - partie en cours avec un autre pseudo : refus ;
    - aucune partie en cours (jamais lancée, terminée, plantée ou abandonnée) : nouvelle partie,
      qui remplace la session précédente.
    """
    refusal = can_join(player_id)
    if refusal is not None:
        logger.warning("Connexion refusée pour %r : %s", player_id, refusal)
        return refusal
    if _game_running():
        return None  # reprise de sa propre partie

    previous = current_session()
    if previous is not None:
        previous.stop()  # le relais de la partie précédente tourne encore
    names = {player_id: player_id, **AI_NAMES}
    start_game(player_id, names, GAME_CONFIG["personality_names"], GAME_CONFIG["seed"])
    return None


def abandon_game(player_id: str) -> bool:
    """Arrête la partie en cours de ce joueur. Renvoie False s'il n'a pas de partie en cours.

    L'annulation interrompt le moteur où qu'il soit (attente du joueur, appel à un LLM).
    """
    session = current_session()
    if session is None or not session.running or session.human_id != player_id:
        return False
    session.stop()
    set_current_session(None)
    logger.info("Partie abandonnée par %s", player_id)
    return True
