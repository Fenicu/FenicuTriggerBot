import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.schemas.chat_settings import UpdateChatFullSettingsRequest
from app.schemas.trigger import TriggerCreate, TriggerUpdate


@pytest.mark.parametrize(
    "payload",
    [
        {"captcha_max_attempts": 0},
        {"captcha_max_attempts": 11},
        {"captcha_timeout": 59},
        {"captcha_timeout": 601},
        {"captcha_ban_duration": 3599},
        {"captcha_ban_duration": 604801},
        {"warn_limit": 1},
        {"warn_limit": 2**31},
        {"warn_duration": -1},
        {"warn_duration": 604801},
        {"tags_weight_messages": -1},
        {"tags_weight_reactions": 2**31},
        {"tags_weight_replies": -1},
        {"tags_daily_message_limit": 0},
        {"tags_daily_reaction_limit": 2**31},
        {"tags_thresholds": [1, 2, 3, 4, 2**31]},
        {"tags_thresholds": [True, 2, 3, 4, 5]},
        {"tags_custom": {"1": "a" * 17}},
        {"tags_custom": {"bad": "tag"}},
        {"settings_locked_sections": ["x" * 1000]},
        {"settings_locked_sections": ["general"] * 9},
        {"welcome_message": {"text": "x" * 65537}},
        {"welcome_message": {"text": "hi", "extra": "x" * 65537}},
        {"welcome_message": {"text": "hi", "reply_markup": "invalid"}},
        {"language_code": "a" * 11},
        {"captcha_max_attempts": None},
    ],
)
async def test_invalid_chat_settings_return_422(payload):
    app = FastAPI()

    @app.patch("/settings")
    async def update(payload: UpdateChatFullSettingsRequest):
        return payload.model_dump()

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.patch("/settings", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("model", [TriggerCreate, TriggerUpdate])
@pytest.mark.parametrize("content", [{"text": "x" * 65537}, {"extra": "x" * 65537}, {"text": {"bad": "type"}}])
async def test_invalid_trigger_content_returns_422(model, content):
    app = FastAPI()

    async def update(payload):
        return payload.model_dump()

    update.__annotations__["payload"] = model
    app.post("/trigger")(update)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/trigger", json={"chat_id": 1, "key_phrase": "test", "content": content})
    assert response.status_code == 422


def test_bot_limits_and_nullable_payloads_accepted():
    request = UpdateChatFullSettingsRequest(
        captcha_timeout=600,
        captcha_max_attempts=10,
        captcha_ban_duration=604800,
        warn_limit=2,
        warn_duration=0,
        tags_weight_messages=0,
        tags_daily_message_limit=1,
        tags_thresholds=[1, 2, 3, 4, 5],
        tags_custom={"0": "", "5": "Legend"},
        settings_locked_sections=["general", "welcome"],
        welcome_message=None,
    )
    assert request.captcha_max_attempts == 10
