import asyncio
from collections import Counter
from unittest.mock import AsyncMock

from app.bot.handlers.captcha import on_captcha_callback
from app.services.captcha_service import CaptchaService
from tests.handlers.test_captcha_ephemeral import _make_callback, _make_i18n


async def test_parallel_attempts_consume_each_chance_once(valkey_client):
    await CaptchaService.create_session(-9001, 9001, max_attempts=3)
    results = await asyncio.gather(*(CaptchaService.verify_attempt(-9001, 9001, "wrong") for _ in range(10)))
    assert Counter(str(result) for result in results) == {"retry": 2, "fail": 1, "no_session": 7}


async def test_correct_code_is_claimed_only_once(valkey_client):
    await CaptchaService.create_session(-9002, 9002)
    stored = await CaptchaService.get_session(-9002, 9002)
    results = await asyncio.gather(
        *(CaptchaService.verify_attempt(-9002, 9002, stored.correct_code) for _ in range(10))
    )
    assert Counter(str(result) for result in results) == {"success": 1, "no_session": 9}


async def test_missing_session_only_answers_callback(db_session, valkey_client, monkeypatch):
    callback = _make_callback(chat_id=-9003, user_id=9003)
    callback.data = "cap:9003:wrong"
    fail = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.captcha._handle_fail", fail)

    await on_captcha_callback(callback, db_session, _make_i18n())

    callback.answer.assert_awaited_once()
    fail.assert_not_awaited()


async def test_regeneration_cannot_revive_exhausted_session(valkey_client):
    await CaptchaService.create_session(-9004, 9004, max_attempts=3)

    async def attempt_and_refresh():
        result = await CaptchaService.verify_attempt(-9004, 9004, "wrong")
        if str(result) == "retry":
            await CaptchaService.regenerate_session(-9004, 9004)
        return str(result)

    results = await asyncio.gather(*(attempt_and_refresh() for _ in range(10)))
    assert Counter(results) == {"retry": 2, "fail": 1, "no_session": 7}
    assert await CaptchaService.get_session(-9004, 9004) is None
