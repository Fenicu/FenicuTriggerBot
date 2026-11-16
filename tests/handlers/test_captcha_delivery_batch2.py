from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError

from app.bot.handlers.chat_member import on_chat_member_update
from app.db.models.captcha_session import CaptchaSessionStatus
from tests.factories import create_chat
from tests.handlers.test_captcha_ephemeral import (
    CHAT_ID,
    USER_ID,
    _fetch_session,
    _make_i18n,
    _make_join_event,
    _make_mock_bot,
)


@pytest.mark.parametrize("stage", ["restrict", "send"])
@pytest.mark.parametrize("error_cls", [TelegramNetworkError, TelegramRetryAfter, TelegramServerError])
async def test_transient_delivery_failure_keeps_session_and_kick(db_session, monkeypatch, stage, error_cls):
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    bot = _make_mock_bot()
    extra = {"retry_after": 30} if error_cls is TelegramRetryAfter else {}
    error = error_cls(method=MagicMock(), message="Temporary failure", **extra)
    if stage == "restrict":
        bot.restrict_chat_member.side_effect = error
    else:
        bot.send_message.side_effect = error
    publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker.publish", publish)

    await on_chat_member_update(_make_join_event(CHAT_ID, USER_ID), db_session, _make_i18n())

    routes = [call.kwargs["routing_key"] for call in publish.await_args_list]
    assert "q.captcha.kick" in routes
    assert "q.captcha.send" in routes
    for call in bot.restrict_chat_member.await_args_list:
        assert call.kwargs["permissions"].can_send_messages is False
    captcha = await _fetch_session(db_session)
    assert captcha.status == CaptchaSessionStatus.PENDING


async def test_telegram_delivery_runs_outside_database_transaction(db_session, monkeypatch):
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    bot = _make_mock_bot()

    async def restrict(*args, **kwargs):
        assert not db_session.in_transaction()

    async def send(*args, **kwargs):
        assert not db_session.in_transaction()
        return MagicMock(message_id=0, ephemeral_message_id=102)

    bot.restrict_chat_member.side_effect = restrict
    bot.send_message.side_effect = send
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker.publish", AsyncMock())

    await on_chat_member_update(_make_join_event(CHAT_ID, USER_ID), db_session, _make_i18n())

    captcha = await _fetch_session(db_session)
    assert captcha.ephemeral_message_id == 102


async def test_retry_worker_sends_same_layout_and_is_idempotent(db_session, monkeypatch):
    from app.services.captcha_service import CaptchaService
    from app.worker.captcha import retry_captcha_delivery
    from tests.factories import create_user
    from tests.handlers.test_captcha_ephemeral import _seed_session

    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    await create_user(db_session, id=USER_ID)
    captcha = await _seed_session(db_session)
    await CaptchaService.create_session(CHAT_ID, USER_ID)
    layout = await CaptchaService.get_session(CHAT_ID, USER_ID)
    bot = _make_mock_bot()
    bot.send_message.return_value = MagicMock(message_id=501)
    monkeypatch.setattr("app.worker.captcha.bot", bot)
    monkeypatch.setattr("app.worker.captcha.translator_hub.get_translator_by_locale", lambda _: _make_i18n())

    await retry_captcha_delivery(CHAT_ID, USER_ID, captcha.id)
    await retry_captcha_delivery(CHAT_ID, USER_ID, captcha.id)

    bot.send_message.assert_awaited_once()
    assert "ephemeral_message_parameters" not in bot.send_message.await_args.kwargs
    keyboard = bot.send_message.await_args.kwargs["reply_markup"]
    assert any(
        button.callback_data == f"cap:{USER_ID}:{layout.correct_code}"
        for row in keyboard.inline_keyboard
        for button in row
    )
    await db_session.refresh(captcha)
    assert captcha.message_id == 501


async def test_known_missing_send_rights_expire_session_before_unrestricting(db_session, monkeypatch):
    from aiogram.exceptions import TelegramBadRequest
    from app.core import permissions

    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    bot = _make_mock_bot()
    bot.send_message.side_effect = TelegramBadRequest(method=MagicMock(), message="CHAT_WRITE_FORBIDDEN")
    publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker.publish", publish)
    try:
        await on_chat_member_update(_make_join_event(CHAT_ID, USER_ID), db_session, _make_i18n())
        captcha = await _fetch_session(db_session)
        await db_session.refresh(captcha)
        assert captcha.status == CaptchaSessionStatus.EXPIRED
        assert bot.restrict_chat_member.await_args.kwargs["permissions"].can_send_messages is True
        assert all(call.kwargs["routing_key"] != "q.captcha.send" for call in publish.await_args_list)
    finally:
        await permissions.clear_for_chat(CHAT_ID)


async def test_undeliverable_captcha_can_retry_failed_permission_restoration(db_session, monkeypatch):
    from app.core import permissions
    from app.worker.captcha import restore_verified_user

    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    await permissions.record_missing(CHAT_ID, "can_send_messages")
    bot = _make_mock_bot()
    bot.restrict_chat_member.side_effect = [TelegramNetworkError(method=MagicMock(), message="Offline"), None]
    publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", bot)
    monkeypatch.setattr("app.worker.captcha.bot", bot)
    monkeypatch.setattr("app.core.safe_telegram.broker.publish", publish)
    try:
        await on_chat_member_update(_make_join_event(CHAT_ID, USER_ID), db_session, _make_i18n())
        assert publish.await_args.kwargs["routing_key"] == "q.captcha.restore"
        await restore_verified_user(**publish.await_args.kwargs["message"])
        assert bot.restrict_chat_member.await_count == 2
    finally:
        await permissions.clear_for_chat(CHAT_ID)
