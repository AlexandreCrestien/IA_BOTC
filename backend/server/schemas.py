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
