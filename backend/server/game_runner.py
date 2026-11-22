"""Lance la partie dans le même processus que le serveur, à la première connexion du joueur humain.
Une seule partie à la fois : la session courante (backend/server/session.py).

Un joueur connecté joue avec le pseudo de son compte, et sa partie est enregistrée (game_records.py).
Un invité ne peut pas prendre le pseudo d'un compte."""
import asyncio
import logging
import random
from typing import Optional

from backend.accounts.pseudo import INVALID_PSEUDO, pseudo_is_valid
from backend.accounts.service import find_by_pseudo
from backend.db import GameStatus, User, get_session, pseudo_key
from backend.engine.config import AI_NAMES, PERSONALITY_NAMES
from backend.engine.setup import setup_game
from backend.models import Alignment
from backend.server.game_records import close_record, new_guest_token, open_record, outcome_for
from backend.server.protocol import forward_requests, send_game_interrupted
from backend.server.session import GameSession, current_session, set_current_session
from backend.engine.turn import play_turn

logger = logging.getLogger(__name__)

# Configuration de la partie. Le joueur humain prend le pseudo qu'il choisit à la connexion.
GAME_CONFIG = {
    "personality_names": PERSONALITY_NAMES,
    "seed": None,  # tests : fixer une graine pour rejouer la même partie
}

# Camp vainqueur, tel qu'envoyé au front (qui écrit le titre et compare au camp du joueur)
WINNER_TEAMS = {Alignment.GOOD: "good", Alignment.EVIL: "evil"}

# Motifs de refus envoyés au front (affichés sur l'écran d'accueil).
# Règles du pseudo : backend/accounts/pseudo.py
REFUSED_PSEUDO = INVALID_PSEUDO
REFUSED_BUSY = "Une partie est déjà en cours avec un autre joueur."
REFUSED_ACCOUNT_PSEUDO = "Ce pseudo appartient à un joueur. Connectez-vous pour l'utiliser."
REFUSED_OTHER_ACCOUNT = "Vous êtes connecté : jouez avec le pseudo de votre compte."
REFUSED_OWNER = "Votre session a expiré : reconnectez-vous pour reprendre votre partie"


def front_ballots(result) -> list[dict]:
    """Bulletins du tour pour le front, depuis ceux du moteur (mention outre-tombe),
    plus les agents dont l'IA n'a pas répondu (abstention signalée)."""
    return [
        {"voter": b.voter, "target": b.target, "ghost": b.ghost, "unavailable": b.voter in result.vote_failures}
        for b in result.ballots
    ]


async def run_game(session: GameSession, names: dict[str, str], personality_names: list[str], seed=None):
    rng = random.Random(seed)
    state, agents, memory = setup_game(names, session.human_id, personality_names, rng)
    session.state, session.memory, session.agents = state, memory, agents
    open_record(session)  # joueur connecté (ou invité déjà inscrit pendant la mise en place)
    port = session.port

    while True:
        turn = state.turn
        result = await play_turn(state, rng, agents, memory, session.human_id, port)
        state = result.state
        session.facts.record_turn(session.human_id, turn, result)
        # Même file que les messages du moteur : le front reçoit tout dans l'ordre
        # (sinon la fin de partie pourrait arriver avant les morts de la dernière nuit).
        await port.show_turn_result(state, turn, front_ballots(result), result.executed)

        if result.game_winner is not None:
            logger.info("Partie terminée, vainqueur : %s", result.game_winner)
            close_record(session, outcome_for(state, session.human_id, result.game_winner), turns=state.turn)
            await port.show_game_over(state, WINNER_TEAMS[result.game_winner],
                                      "Le village a rendu son dernier verdict.", achievements=session.unlocked)
            return state


def _on_game_end(session: GameSession, task: asyncio.Task) -> None:
    """Fin de la tâche de partie. Si elle a planté, le joueur est prévenu (sinon son écran resterait figé)."""
    if task.cancelled():
        return  # abandon : le joueur a déjà été prévenu
    error = task.exception()
    if error is not None:
        logger.error("Partie interrompue", exc_info=error)
        close_record(session, GameStatus.INTERRUPTED)  # problème serveur : hors statistiques
        asyncio.ensure_future(send_game_interrupted(session.human_id))


def start_game(human_id: str, names: dict[str, str], personality_names: list[str], seed=None,
               user_id: Optional[int] = None) -> GameSession:
    """Crée la session et lance la partie, avec le relais de ses demandes vers le front.
    user_id : compte du joueur, None pour un invité (qui reçoit un jeton pour rattacher la partie s'il s'inscrit).
    Doit être appelée depuis une coroutine."""
    session = GameSession(human_id=human_id, user_id=user_id,
                          guest_token=None if user_id is not None else new_guest_token())
    set_current_session(session)
    session.forward_task = asyncio.create_task(forward_requests(session))
    session.game_task = asyncio.create_task(run_game(session, names, personality_names, seed))
    session.game_task.add_done_callback(lambda task: _on_game_end(session, task))
    return session


def _game_running() -> bool:
    session = current_session()
    return session is not None and session.running


def _is_account_pseudo(pseudo: str) -> bool:
    with get_session() as db:
        return find_by_pseudo(db, pseudo) is not None


def can_join(player_id: str, user: Optional[User] = None) -> Optional[str]:
    """Le joueur peut-il entrer ? None si oui, sinon le motif du refus. Ne lance rien.
    user : compte connecté (cookie), None pour un invité."""
    if not pseudo_is_valid(player_id):
        return REFUSED_PSEUDO
    if _game_running():
        session = current_session()
        if player_id != session.human_id:
            return REFUSED_BUSY
        if session.user_id is not None and (user is None or user.id != session.user_id):
            return REFUSED_OWNER
        return None  # reprise de sa propre partie
    # Nouvelle partie : un compte joue sous son pseudo, un invité ne peut pas prendre celui d'un compte
    if user is not None:
        return None if pseudo_key(player_id) == user.pseudo_key else REFUSED_OTHER_ACCOUNT
    return REFUSED_ACCOUNT_PSEUDO if _is_account_pseudo(player_id) else None


def ensure_started(player_id: str, user: Optional[User] = None) -> Optional[str]:
    """Appelée à chaque connexion. Renvoie None si le joueur peut jouer, sinon le motif du refus.

    - partie en cours avec ce pseudo : reprise (le serveur renvoie l'état et la demande en attente) ;
    - partie en cours avec un autre pseudo : refus ;
    - aucune partie en cours (jamais lancée, terminée, plantée ou abandonnée) : nouvelle partie,
      qui remplace la session précédente.
    """
    refusal = can_join(player_id, user)
    if refusal is not None:
        logger.warning("Connexion refusée pour %r : %s", player_id, refusal)
        return refusal
    if _game_running():
        return None  # reprise de sa propre partie

    previous = current_session()
    if previous is not None:
        previous.stop()  # le relais de la partie précédente tourne encore
    names = {player_id: player_id, **AI_NAMES}
    start_game(player_id, names, GAME_CONFIG["personality_names"], GAME_CONFIG["seed"],
               user_id=user.id if user is not None else None)
    return None


def abandon_game(player_id: str) -> bool:
    """Arrête la partie en cours de ce joueur. Renvoie False s'il n'a pas de partie en cours.

    L'annulation interrompt le moteur où qu'il soit (attente du joueur, appel à un LLM).
    """
    session = current_session()
    if session is None or not session.running or session.human_id != player_id:
        return False
    close_record(session, GameStatus.ABANDONED)  # défaite (abandon)
    session.stop()
    set_current_session(None)
    logger.info("Partie abandonnée par %s", player_id)
    return True
