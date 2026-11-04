from typing import Literal, Optional, List, Union
from pydantic import BaseModel

class SendChatPayload(BaseModel):
    channel_id: str
    content: str

class SendChatAction(BaseModel):
    action: Literal["send_chat"] = "send_chat"
    payload: SendChatPayload

class NightActionPayload(BaseModel):
    targets: List[str]

class NightAction(BaseModel):
    action: Literal["night_action"] = "night_action"
    payload: NightActionPayload


ClientActionPacket = Union[SendChatAction, NightAction]