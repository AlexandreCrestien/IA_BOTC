"""Lance la partie dans le même processus que le serveur, à la première connexion du joueur humain."""
import asyncio
import logging
import random
from typing import Optional

from backend.game_engine import setup_game
from backend.human_port import QueueHumanPort
from backend.human_turns import play_turn_with_human
from backend.models import Alignement
from backend.server.websockets import register_human, reset_player, send_game_interrupted

logger = logging.getLogger(__name__)

# Noms des 5 agents IA (identifiant -> nom affiché)
AI_NAMES = {
    "p1": "marIA",
    "p2": "tobIAs",
    "p3": "mAIsie",
    "p4": "adrIAn",
    "p5": "dIAne",
}

# Configuration de la partie. Le joueur humain prend le pseudo qu'il choisit à la connexion.
GAME_CONFIG = {
    "personality_names": ["agitator", "clown", "observer", "paranoid", "strategist"],
    "seed": None,  # tests : fixer une graine pour rejouer la même partie
}

# Libellés affichés par le front (il reconnaît le camp du joueur au mot « Démon »)
WINNER_LABELS = {
    Alignement.BON: "Villageois",
    Alignement.MAUVAIS: "Démons",
}

# Une seule partie à la fois : la tâche qui la fait tourner et le pseudo du joueur humain.
_current: Optional[asyncio.Task] = None
_current_human: Optional[str] = None

# Motifs de refus envoyés au front (affichés sur l'écran d'accueil)
REFUSED_PSEUDO = "Ce pseudo est réservé ou invalide : choisissez-en un autre."
REFUSED_BUSY = "Une partie est déjà en cours avec un autre joueur."


def _winner_label(winner) -> str:
    return WINNER_LABELS.get(winner, str(winner))


def _all_players(state):
    players = state.players
    return players.values() if isinstance(players, dict) else players


async def run_game(names: dict[str, str], human_id: str, personality_names: list[str], seed=None):
    rng = random.Random(seed)
    state, agents, memory = setup_game(names, human_id, personality_names, rng)
    port = QueueHumanPort()
    port.memory = memory
    port.state = state
    port.agents = agents  # lus par la route d'administration (personnalités)
    register_human(human_id, port)

    while True:
        turn = state.turn
        result = await play_turn_with_human(state, rng, agents, memory, human_id, port)
        state = result.state
        port.state = state
        port.votes_history.append({"turn": turn, "votes": result.votes, "executed": result.executed})

        # Le front reçoit des noms, jamais des identifiants internes
        label = {p.id: p.name for p in _all_players(state)}
        votes = [
            {"voter": label.get(voter, voter), "target": label.get(target, target) if target else None}
            for voter, target in result.votes.items()
        ]
        executed = label.get(result.executed, result.executed) if result.executed else None
        # Même file que les messages du moteur : le front reçoit tout dans l'ordre
        # (sinon la fin de partie pourrait arriver avant les morts de la dernière nuit).
        await port.requests.put({"kind": "vote_result", "turn": turn, "executed": executed, "votes": votes})

        if result.game_winner is not None:
            logger.info("Partie terminée, vainqueur : %s", result.game_winner)
            await port.requests.put({
                "kind": "game_over",
                "winner": _winner_label(result.game_winner),
                "details": "Le village a rendu son dernier verdict.",
            })
            return state


def _game_running() -> bool:
    return _current is not None and not _current.done()


def _on_game_end(task: asyncio.Task) -> None:
    """Fin de la tâche de partie. Si elle a planté, le joueur est prévenu (sinon son écran resterait figé)."""
    if task.cancelled():
        return  # abandon : le joueur a déjà été prévenu
    error = task.exception()
    if error is not None:
        logger.error("Partie interrompue", exc_info=error)
        if _current_human is not None:
            asyncio.ensure_future(send_game_interrupted(_current_human))


def start_game(names, human_id, personality_names, seed=None) -> asyncio.Task:
    """Lance la partie si aucune n'est en cours. Doit être appelée depuis une coroutine."""
    global _current, _current_human
    if _game_running():
        return _current
    _current_human = human_id
    _current = asyncio.create_task(run_game(names, human_id, personality_names, seed))
    _current.add_done_callback(_on_game_end)
    return _current


def _pseudo_is_valid(pseudo: str) -> bool:
    """Refuse un pseudo vide, réservé, ou déjà pris par un agent (sans tenir compte de la casse)."""
    taken = {k.casefold() for k in AI_NAMES} | {v.casefold() for v in AI_NAMES.values()} | {"game_master"}
    return pseudo.strip() != "" and pseudo.casefold() not in taken


def can_join(player_id: str) -> Optional[str]:
    """Le joueur peut-il entrer ? None si oui, sinon le motif du refus. Ne lance rien."""
    if not _pseudo_is_valid(player_id):
        return REFUSED_PSEUDO
    if _game_running() and player_id != _current_human:
        return REFUSED_BUSY
    return None


def ensure_started(player_id: str) -> Optional[str]:
    """Appelée à chaque connexion. Renvoie None si le joueur peut jouer, sinon le motif du refus.

    - partie en cours avec ce pseudo : reprise (le serveur renvoie l'état et la demande en attente) ;
    - partie en cours avec un autre pseudo : refus ;
    - aucune partie en cours (jamais lancée, terminée, plantée ou abandonnée) : nouvelle partie.
    """
    refusal = can_join(player_id)
    if refusal is not None:
        logger.warning("Connexion refusée pour %r : %s", player_id, refusal)
        return refusal
    if _game_running():
        return None  # reprise de sa propre partie

    # Les traces de la partie précédente ne doivent pas déborder sur la nouvelle
    if _current_human is not None:
        reset_player(_current_human)
    names = {player_id: player_id, **AI_NAMES}
    start_game(names, player_id, GAME_CONFIG["personality_names"], GAME_CONFIG["seed"])
    return None


def abandon_game(player_id: str) -> bool:
    """Arrête la partie en cours de ce joueur. Renvoie False s'il n'a pas de partie en cours.

    L'annulation interrompt le moteur où qu'il soit (attente du joueur, appel à un LLM).
    """
    global _current, _current_human
    if not _game_running() or player_id != _current_human:
        return False
    _current.cancel()
    reset_player(player_id)
    _current = None
    _current_human = None
    logger.info("Partie abandonnée par %s", player_id)
    return True