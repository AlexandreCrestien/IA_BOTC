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
    target_agent_id: str = Field(..., description="ID de l'agent dont on répond à l'invitation")
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


class TriggerVotePhasePayload(StrictInput):
    pass  # Aucun paramètre requis pour l'instant

class TriggerVotePhaseAction(BaseAction):
    """Déclencher le passage à la phase de vote."""
    action: Literal["trigger_vote_phase"] = "trigger_vote_phase"
    payload: TriggerVotePhasePayload = Field(default_factory=TriggerVotePhasePayload)


# Le type d'action est choisi uniquement d'après le champ "action" (obligatoire dans le paquet reçu).
ClientActionPacket = Annotated[
    Union[
        SendChatAction,
        RequestWhisperAction,
        RespondWhisperInvitationAction,
        SubmitVoteAction,
        SubmitNightAction,
        TriggerVotePhaseAction,  # <--- AJOUTÉ ICI
    ],
    Field(discriminator="action"),
]


# OUTPUTS / DTO (DATA TRANSFER OBJECT)

class PlayerPublicDTO(BaseModel):
    """Informations publiques visibles par tout le monde sur la table de jeu."""
    id: str
    name: str
    alive: bool
    has_vote: bool = Field(..., description="Vrai si le joueur a encore son vote (gère le dernier vote des joueurs morts)")


class HumanRoleDTO(BaseModel):
    """Informations strictement privées sur le rôle de l'humain."""
    name_fr: str
    power_description: str
    team: str
    alignment: str


class ChannelDTO(BaseModel):
    id: str
    name: str
    public: bool
    members: List[str]
    open: bool


class NightLogDTO(BaseModel):
    """Représente une information reçue lors d'une nuit spécifique."""
    night_number: int
    content: str


class VoteRecordDTO(BaseModel):
    """Représente un vote enregistré lors de la phase de jugement."""
    turn: int
    voter: str
    target: Optional[str] = Field(default=None, description="Nom/ID du joueur visé ou None si vote blanc")
    executed: Optional[str] = Field(default=None, description="Nom du joueur exécuté ce jour-là, s'il y en a un")
  

class GameStateDTO(BaseModel):
    """L'état global de la partie, envoyé à un joueur spécifique."""
    turn: int
    phase: str 
    players: List[PlayerPublicDTO]
    channels: List[ChannelDTO]
    my_role: Optional[HumanRoleDTO] = None
    night_history: List[NightLogDTO] = Field(
        default_factory=list, 
        description="Historique de toutes les révélations nocturnes reçues depuis le début de la partie"
    )
    vote_history: List[VoteRecordDTO] = Field(
        default_factory=list,
        description="Historique complet des votes passés"
    )


class ServerMessage(BaseModel):
    """Format standard des messages envoyés par le serveur vers le client via WebSocket."""
    type: Literal["state_update", "chat_message", "night_request", "vote_request", "error"]
    data: Union[GameStateDTO, dict, str]