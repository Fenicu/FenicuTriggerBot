"""Валидация welcome_message в UpdateChatFullSettingsRequest."""

import pytest
from pydantic import ValidationError

from app.schemas.chat_settings import UpdateChatFullSettingsRequest


def test_story_welcome_message_rejected():
    with pytest.raises(ValidationError, match="story"):
        UpdateChatFullSettingsRequest(welcome_message={"story": {"id": 1}})


def test_text_welcome_message_accepted():
    request = UpdateChatFullSettingsRequest(welcome_message={"text": "Hello"})

    assert request.welcome_message == {"text": "Hello"}


def test_photo_welcome_message_accepted():
    request = UpdateChatFullSettingsRequest(
        welcome_message={"photo": [{"file_id": "abc"}], "caption": "Hi"}
    )

    assert request.welcome_message is not None


def test_legacy_copy_without_story_accepted_by_schema():
    request = UpdateChatFullSettingsRequest(
        welcome_message={"message_id": 10, "chat": {"id": -100, "type": "supergroup"}}
    )

    assert request.welcome_message is not None
