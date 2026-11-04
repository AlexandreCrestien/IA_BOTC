import pytest
from pydantic import ValidationError

from backend.models import Channel, Message, Phase


def private_channel() -> Channel:
    return Channel(id="s1", name="Odette et Silas", members=("odette", "silas"))


def message(author: str = "odette", text: str = "Attendons.") -> Message:
    return Message(author_id=author, text=text, turn=2, phase=Phase.DISCUSSION)


def test_new_channel_is_open_without_messages():
    c = private_channel()
    assert c.open and c.messages == ()


def test_member_can_write():
    c = private_channel().add_message(message("odette"))
    assert len(c.messages) == 1


def test_non_member_cannot_write():
    with pytest.raises(ValueError):
        private_channel().add_message(message("brutus"))


def test_member_sees_history():
    c = private_channel().add_message(message("odette"))
    assert c.messages_visible_to("silas") == c.messages


def test_non_member_sees_nothing():
    c = private_channel().add_message(message("odette"))
    assert c.messages_visible_to("brutus") == ()


def test_close_keeps_history_readable():
    c = private_channel().add_message(message("odette")).close()
    assert not c.open and len(c.messages) == 1 and c.messages_visible_to("odette") == c.messages


def test_closed_channel_refuses_messages():
    c = private_channel().close()
    with pytest.raises(ValueError):
        c.add_message(message("odette"))


def test_closing_twice_refused():
    with pytest.raises(ValueError):
        private_channel().close().close()


def test_added_member_can_write():
    c = private_channel().add_member("brutus")
    assert c.add_message(message("brutus")).messages[0].author_id == "brutus"


def test_adding_existing_member_refused():
    with pytest.raises(ValueError):
        private_channel().add_member("odette")


def test_channel_without_member_refused():
    with pytest.raises(ValidationError):
        Channel(id="s1", name="Vide", members=())


def test_empty_message_refused():
    with pytest.raises(ValidationError):
        message(text="")


def test_channel_is_immutable():
    with pytest.raises(ValidationError):
        private_channel().name = "autre"