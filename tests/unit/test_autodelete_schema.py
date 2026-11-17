"""Валидация autodelete_settings: типы сервисных сообщений о входе/выходе."""

import pytest
from app.schemas.chat_settings import UpdateChatFullSettingsRequest
from pydantic import ValidationError


@pytest.mark.parametrize("key", ["service_join", "service_leave"])
def test_service_autodelete_type_accepted(key):
    request = UpdateChatFullSettingsRequest(autodelete_settings={key: {"enabled": True, "delay": 120}})

    assert request.autodelete_settings == {key: {"enabled": True, "delay": 120}}


@pytest.mark.parametrize("key", ["service_join", "service_leave"])
def test_service_autodelete_type_fills_default_delay(key):
    request = UpdateChatFullSettingsRequest(autodelete_settings={key: {"enabled": False}})

    assert request.autodelete_settings == {key: {"enabled": False, "delay": 30}}


@pytest.mark.parametrize("key", ["service_join", "service_leave"])
@pytest.mark.parametrize("delay", [0, 3601, "30", None])
def test_service_autodelete_type_rejects_bad_delay(key, delay):
    with pytest.raises(ValidationError, match=f"autodelete delay for '{key}' must be int 1-3600"):
        UpdateChatFullSettingsRequest(autodelete_settings={key: {"enabled": True, "delay": delay}})


@pytest.mark.parametrize("key", ["service_join", "service_leave"])
def test_service_autodelete_type_requires_enabled_bool(key):
    with pytest.raises(ValidationError, match=f"autodelete config for '{key}' must have 'enabled'"):
        UpdateChatFullSettingsRequest(autodelete_settings={key: {"delay": 10}})
