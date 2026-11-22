from typing import Annotated, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


# INPUTS

class StrictInput(BaseModel):
    """Base des messages reçus du client : un champ inconnu est une erreur,
    pour qu'une faute de frappe ne passe pas silencieusement (ex. 'targets' au lieu de 'target_id')."""
    model_config = ConfigDict(extra="forbid")


class BaseAction(StrictInput):
    action: str


class SendChatPayload(StrictInput):
    channel_id: str = Field(..., description="ID du salon (ex: 'public' ou ID d'un salon privé)")
    content: str = Field(..., min_length=1, description="Contenu du message")

class SendChatAction(BaseAction):
    """Poster un message dans un canal public ou privé."""
    action: Literal["send_chat"] = "send_chat"
    payload: SendChatPayload


class RequestWhisperPayload(StrictInput):
    targets: List[str] = Field(..., min_length=1, max_length=2, description="1 ou 2 agents avec qui lancer la conversation privée")

class RequestWhisperAction(BaseAction):
    """Demander un entretien/chuchotement avec 1 ou 2 agents."""
    action: Literal["request_whisper"] = "request_whisper"
    payload: RequestWhisperPayload


class RespondWhisperPayload(StrictInput):
    target_agent_id: str = Field(..., description="Nom de l'agent dont on répond à l'invitation")
    accepted: bool = Field(..., description="Vrai si accepté, Faux si refusé")

class RespondWhisperInvitationAction(BaseAction):
    """Accepter ou refuser une invitation de chuchotement d'un agent."""
    action: Literal["respond_whisper_invitation"] = "respond_whisper_invitation"
    payload: RespondWhisperPayload


class SubmitVotePayload(StrictInput):
    target_id: Optional[str] = Field(default=None, description="ID du joueur visé pour l'exécution, ou None pour voter blanc/personne")

class SubmitVoteAction(BaseAction):
    """Choisir contre qui voter lors de la phase d'exécution."""
    action: Literal["submit_vote"] = "submit_vote"
    payload: SubmitVotePayload


class SubmitNightActionPayload(StrictInput):
    targets: List[str] = Field(default_factory=list, description="Cible(s) choisie(s) pour le pouvoir de nuit")

class SubmitNightAction(BaseAction):
    """Effectuer l'action de nuit selon le rôle du joueur."""
    action: Literal["submit_night_action"] = "submit_night_action"
    payload: SubmitNightActionPayload


class DiscussionTimeoutPayload(StrictInput):
    pass

class DiscussionTimeoutAction(BaseAction):
    """Le joueur n'a pas choisi de salon privé à temps : un agent va lui proposer un entretien."""
    action: Literal["discussion_timeout"] = "discussion_timeout"
    payload: DiscussionTimeoutPayload = Field(default_factory=DiscussionTimeoutPayload)


class SkipTurnPayload(StrictInput):
    kind: Literal["public_message", "private_message", "private_partners"] = Field(
        ..., description="Étape facultative à passer : message public, message privé (fin du salon), salon privé")

class SkipTurnAction(BaseAction):
    """Passer une étape facultative attendue par le moteur."""
    action: Literal["skip_turn"] = "skip_turn"
    payload: SkipTurnPayload


class AbandonGamePayload(StrictInput):
    pass

class AbandonGameAction(BaseAction):
    """Abandonner la partie en cours (le joueur revient à l'accueil)."""
    action: Literal["abandon_game"] = "abandon_game"
    payload: AbandonGamePayload = Field(default_factory=AbandonGamePayload)


# Le type d'action est choisi uniquement d'après le champ "action" (obligatoire dans le paquet reçu).
ClientActionPacket = Annotated[
    Union[
        SendChatAction,
        RequestWhisperAction,
        RespondWhisperInvitationAction,
        SubmitVoteAction,
        SubmitNightAction,
        DiscussionTimeoutAction,
        SkipTurnAction,
        AbandonGameAction,
    ],
    Field(discriminator="action"),
]


# OUTPUTS : messages envoyés au front (static/js/connection.js, handleServerMessage)
# Les joueurs sont toujours désignés par leur identifiant ; le front affiche leur nom
# grâce à la liste des joueurs de game_state.

class OutMessage(BaseModel):
    """Base des messages envoyés au front : un champ inconnu est une erreur de programmation."""
    model_config = ConfigDict(extra="forbid")


class FrontPlayer(OutMessage):
    id: str
    name: str
    alive: bool
    has_vote: bool = Field(..., description="Mort : voix d'outre-tombe encore disponible ou non")


class FrontGameState(OutMessage):
    day: int
    phase: Literal["nuit", "discussion", "vote"]
    aliveCount: int
    players: List[FrontPlayer]


class Ally(OutMessage):
    id: str
    role: str = Field(..., description="Nom français du rôle")


class Ballot(OutMessage):
    voter: str
    target: Optional[str] = Field(..., description="None : vote pour personne")
    ghost: bool = Field(..., description="Votant déjà mort qui a voté : voix d'outre-tombe utilisée")
    unavailable: bool = Field(default=False, description="L'IA du votant n'a pas répondu : abstention forcée")


class NightHistoryEntry(OutMessage):
    turn: int
    type: Literal["role_info", "result"]
    info: Optional[str] = Field(default=None, description="role_info : texte de l'information")
    dead_player: Optional[str] = Field(default=None, description="result : mort de la nuit (None : personne)")


class VoteHistoryEntry(OutMessage):
    turn: int
    voter: str
    target: Optional[str]
    executed: Optional[str]
    unavailable: bool = False


class Connected(OutMessage):
    type: Literal["connected"] = "connected"


class GuestSession(OutMessage):
    """Partie d'un invité : jeton à présenter à l'inscription ou à la connexion (pendant la partie ou sur
    l'écran de fin) pour rattacher la partie au compte. Le front le garde en mémoire, sans le montrer."""
    type: Literal["guest_session"] = "guest_session"
    guest_token: str


class RoleAssigned(OutMessage):
    type: Literal["role_assigned"] = "role_assigned"
    role_name: str
    description: str
    allies: Optional[List[Ally]] = Field(default=None, description="Reconnexion d'un joueur du mal après la révélation")


class GameStateMessage(OutMessage):
    type: Literal["game_state"] = "game_state"
    state: FrontGameState


class ActionRequest(OutMessage):
    type: Literal["action_request"] = "action_request"
    kind: Literal["nuit", "vote", "discussion"]
    candidates: List[str]
    max_targets: Optional[int] = None
    min_targets: Optional[int] = None
    role: Optional[str] = Field(default=None, description="Nuit : nom anglais du rôle (textes du front)")


class InputRequest(OutMessage):
    type: Literal["input_request"] = "input_request"
    kind: Literal["public_message", "private_message"]
    channel_id: Optional[str]
    text: str
    left: Optional[int] = Field(default=None, description="Messages privés restants")


class AgentWhisperRequest(OutMessage):
    type: Literal["agent_whisper_request"] = "agent_whisper_request"
    agent_id: str


class ChatMessage(OutMessage):
    type: Literal["chat"] = "chat"
    channel_id: str
    sender: str = Field(..., description="Identifiant du joueur, ou « Codex » pour les annonces")
    content: str


class PrivateChannelOpened(OutMessage):
    type: Literal["private_channel_opened"] = "private_channel_opened"
    channel_id: str
    members: List[str]
    text: str
    focus: bool = Field(default=True, description="False : salon rouvert à la reconnexion, sans s'y placer")


class History(OutMessage):
    type: Literal["history"] = "history"
    nights: List[NightHistoryEntry]
    votes: List[VoteHistoryEntry]


class NightInfo(OutMessage):
    type: Literal["night_info"] = "night_info"
    turn: int
    info: str
    allies: Optional[List[Ally]] = Field(default=None, description="Première nuit, camp du mal uniquement")


class NightResult(OutMessage):
    type: Literal["night_result"] = "night_result"
    turn: int
    dead_player: Optional[str]


class NightActionAck(OutMessage):
    type: Literal["night_action_ack"] = "night_action_ack"
    text: str


class VoteResult(OutMessage):
    type: Literal["vote_result"] = "vote_result"
    turn: int
    executed: Optional[str]
    votes: List[Ballot]


class Announcement(OutMessage):
    type: Literal["announcement"] = "announcement"
    text: str


class Error(OutMessage):
    type: Literal["error"] = "error"
    data: str


class UnlockedAchievementOut(OutMessage):
    """Succès débloqué par la partie, annoncé sur l'écran de fin."""
    code: str
    title: str
    description: str
    message: Optional[str] = None


class GameOver(OutMessage):
    type: Literal["game_over"] = "game_over"
    winner: Literal["good", "evil"]
    details: str
    achievements: List[UnlockedAchievementOut] = Field(default_factory=list)


class GameAbandoned(OutMessage):
    type: Literal["game_abandoned"] = "game_abandoned"


class GameInterrupted(OutMessage):
    type: Literal["game_interrupted"] = "game_interrupted"
    text: str
