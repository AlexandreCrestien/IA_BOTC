"""Validation des actions reçues du front (backend/server/schemas.py) : un paquet mal formé est refusé."""
import pytest
from pydantic import TypeAdapter, ValidationError

from backend.server.schemas import (
    ClientActionPacket,
    DiscussionTimeoutAction,
    RequestWhisperAction,
    RespondWhisperInvitationAction,
    SendChatAction,
    SubmitNightAction,
    SubmitVoteAction,
)

parse_action = TypeAdapter(ClientActionPacket).validate_python

def test_parse_send_chat():
    action = parse_action({"action": "send_chat", "payload": {"channel_id": "public", "content": "Salut"}})
    assert isinstance(action, SendChatAction)
    assert action.payload.content == "Salut"


@pytest.mark.parametrize("targets", [["ana"], ["ana", "bruno"]])
def test_parse_request_whisper_with_one_or_two_agents(targets):
    action = parse_action({"action": "request_whisper", "payload": {"targets": targets}})
    assert isinstance(action, RequestWhisperAction)
    assert action.payload.targets == targets


@pytest.mark.parametrize("targets", [[], ["ana", "bruno", "carla"]])
def test_request_whisper_needs_one_or_two_agents(targets):
    with pytest.raises(ValidationError):
        parse_action({"action": "request_whisper", "payload": {"targets": targets}})


def test_parse_respond_whisper_invitation():
    action = parse_action({"action": "respond_whisper_invitation", "payload": {"target_agent_id": "tobIAs", "accepted": True}})
    assert isinstance(action, RespondWhisperInvitationAction)
    assert action.payload.target_agent_id == "tobIAs"
    assert action.payload.accepted is True


def test_parse_submit_night_action():
    action = parse_action({"action": "submit_night_action", "payload": {"targets": ["ana", "bruno"]}})
    assert isinstance(action, SubmitNightAction)
    assert action.payload.targets == ["ana", "bruno"]


def test_submit_night_action_targets_default_to_empty():
    assert parse_action({"action": "submit_night_action", "payload": {}}).payload.targets == []


def test_parse_vote_for_player():
    action = parse_action({"action": "submit_vote", "payload": {"target_id": "ana"}})
    assert isinstance(action, SubmitVoteAction)
    assert action.payload.target_id == "ana"


def test_vote_for_nobody():
    assert parse_action({"action": "submit_vote", "payload": {"target_id": None}}).payload.target_id is None
    assert parse_action({"action": "submit_vote", "payload": {}}).payload.target_id is None


def test_parse_discussion_timeout():
    action = parse_action({"action": "discussion_timeout", "payload": {}})
    assert isinstance(action, DiscussionTimeoutAction)


def test_empty_chat_message_is_rejected():
    with pytest.raises(ValidationError):
        parse_action({"action": "send_chat", "payload": {"channel_id": "public", "content": ""}})


def test_chat_message_is_limited_to_500_characters():
    # Chaque message du joueur entre dans le contexte des agents : un message géant coûterait des tokens à chaque appel
    parse_action({"action": "send_chat", "payload": {"channel_id": "public", "content": "a" * 500}})
    with pytest.raises(ValidationError):
        parse_action({"action": "send_chat", "payload": {"channel_id": "public", "content": "a" * 501}})


@pytest.mark.parametrize("packet", [
    {"action": "voler_le_role", "payload": {}},   # action inconnue
    {"action": "send_chat"},                      # payload manquant
])
def test_invalid_packets_are_rejected(packet):
    with pytest.raises(ValidationError):
        parse_action(packet)


def test_packet_without_action_is_rejected():
    """Sans "action", le paquet ne doit pas être deviné d'après son contenu."""
    with pytest.raises(ValidationError):
        parse_action({"payload": {"target_id": "ana"}})


def test_unknown_payload_field_is_rejected():
    """Une faute de frappe ('targets' au lieu de 'target_id') ne doit pas devenir un vote pour personne."""
    with pytest.raises(ValidationError):
        parse_action({"action": "submit_vote", "payload": {"targets": ["ana"]}})


def test_unknown_field_in_action_is_rejected():
    with pytest.raises(ValidationError):
        parse_action({"action": "submit_vote", "payload": {"target_id": "ana"}, "joueur": "ana"})
