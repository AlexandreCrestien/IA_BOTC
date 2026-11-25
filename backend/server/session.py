"""La partie en cours (une seule à la fois) et tout ce que le serveur en retient.

Une GameSession regroupe :
- la tâche qui fait tourner le moteur, et celle qui relaie ses demandes au front ;
- le port qui relie le moteur au joueur humain, et la demande à laquelle il doit répondre ;
- l'état, la mémoire et les agents de la partie (lus par le relais et par l'administration) ;
- ce que le front doit retrouver après une reconnexion : chat, salons, alliés, historiques ;
- les messages des agents IA, que le joueur connecté peut signaler (reports.py).
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from backend.engine.human_port import QueueHumanPort
from backend.ai.memory_manager import MemoryManager
from backend.db import GameStatus
from backend.db.models import utcnow
from backend.models import GameState
from backend.stats.achievements import GameFacts

# Demandes du moteur auxquelles le joueur doit répondre
ANSWERABLE = {"night_choice", "vote", "public_message", "private_partners", "private_message", "agent_invitation"}
WHISPER_MESSAGES = 3  # messages privés autorisés par salon


@dataclass
class GameSession:
    human_id: str
    port: QueueHumanPort = field(default_factory=QueueHumanPort)
    game_task: Optional[asyncio.Task] = None
    forward_task: Optional[asyncio.Task] = None

    # Compte du joueur (None : invité). Un invité qui s'inscrit ou se connecte pendant la partie,
    # ou sur l'écran de fin, la rattache à son compte en présentant guest_token (game_records.py).
    user_id: Optional[int] = None
    guest_token: Optional[str] = None
    record_id: Optional[int] = None          # ligne de la table games (parties d'un compte)
    started_at: datetime = field(default_factory=utcnow)
    ended_at: Optional[datetime] = None
    outcome: Optional[GameStatus] = None     # issue de la partie, une fois terminée
    facts: GameFacts = field(default_factory=GameFacts)  # pour les succès (exécution, voix d'outre-tombe…)
    unlocked: list[dict] = field(default_factory=list)   # succès débloqués par cette partie (écran de fin)

    # Partie : renseignés par game_runner, puis l'état est mis à jour à chaque demande du moteur
    state: Optional[GameState] = None
    memory: Optional[MemoryManager] = None
    agents: dict[str, Any] = field(default_factory=dict)

    # Demande du moteur en attente d'une réponse du joueur (redemandée après une reconnexion)
    pending: Optional[dict] = None

    # Salon privé en cours et messages privés restants
    whisper: Optional[str] = None
    whisper_left: int = WHISPER_MESSAGES

    # Renvoyés au front à chaque connexion (il repart d'une page vide)
    role_sent: bool = False            # rôle déjà envoyé sur la connexion actuelle
    chat_log: list[dict] = field(default_factory=list)                 # messages de chat (public et salons)
    opened_channels: dict[str, list[str]] = field(default_factory=dict)  # salon privé -> membres (ids)
    allies: Optional[list[dict]] = None                                # alliés révélés au camp du mal
    night_log: list[dict] = field(default_factory=list)                # onglet Nuits
    vote_log: list[dict] = field(default_factory=list)                 # onglet Votes

    # Messages des agents IA, par identifiant (m1, m2…) : de quoi enregistrer un signalement
    # ({agent, model, turn, phase, channel, message : le ChatMessage envoyé}) ; signalements envoyés
    ai_messages: dict[str, dict] = field(default_factory=dict)
    reports_sent: int = 0
    rated: bool = False  # agents déjà évalués sur l'écran de fin (une seule fois par partie, ratings.py)

    # IA qui n'ont pas répondu : [{turn, phase, agent, step}] (panel admin), et bandeau déjà affiché
    agent_failures: list[dict] = field(default_factory=list)
    failure_banner_shown: bool = False

    @property
    def running(self) -> bool:
        return self.game_task is not None and not self.game_task.done()

    def waits_for(self, kind: str) -> bool:
        return self.pending is not None and self.pending["kind"] == kind

    def answer(self, kind: str, value: Any) -> bool:
        """Donne la réponse au moteur seulement si c'est la demande attendue. Renvoie False sinon."""
        if not self.waits_for(kind):
            return False
        self.pending = None
        self.port.answers.put_nowait(value)
        return True

    def stop(self) -> None:
        """Arrête le moteur et le relais (abandon, ou nouvelle partie)."""
        for task in (self.game_task, self.forward_task):
            if task is not None:
                task.cancel()


_current: Optional[GameSession] = None


def current_session() -> Optional[GameSession]:
    """La partie en cours ou la dernière terminée (None si aucune partie n'a été lancée)."""
    return _current


def set_current_session(session: Optional[GameSession]) -> None:
    global _current
    _current = session
