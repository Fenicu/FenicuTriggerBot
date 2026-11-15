from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from app.core.safe_telegram import restore_captcha_permissions


@pytest.mark.parametrize("error_cls", [TelegramRetryAfter, TelegramNetworkError, TelegramServerError])
async def test_transient_restore_error_schedules_retry(monkeypatch, error_cls):
    extra = {"retry_after": 40} if error_cls is TelegramRetryAfter else {}
    error = error_cls(method=MagicMock(), message="Temporary failure", **extra)
    bot = MagicMock(restrict_chat_member=AsyncMock(side_effect=error))
    publish = AsyncMock()
    record_missing = AsyncMock()
    monkeypatch.setattr("app.core.safe_telegram.broker.publish", publish)
    monkeypatch.setattr("app.core.safe_telegram.permissions.record_missing", record_missing)

    assert await restore_captcha_permissions(bot, -100, 42, 10, attempt=2) is False

    publish.assert_awaited_once()
    assert publish.await_args.kwargs["routing_key"] == "q.captcha.restore"
    assert publish.await_args.kwargs["message"]["attempt"] == 3
    assert publish.await_args.kwargs["headers"]["x-delay"] == (40_000 if extra else 10_000)
    record_missing.assert_not_awaited()


@pytest.mark.parametrize(
    "error_cls,message,permission",
    [
        (TelegramBadRequest, "USER_NOT_PARTICIPANT", None),
        (TelegramForbiddenError, "bot was kicked from the supergroup chat", None),
        (TelegramBadRequest, "not enough rights to restrict/unrestrict chat member", "can_restrict_members"),
        (TelegramBadRequest, "CHAT_ADMIN_REQUIRED", "can_restrict_members"),
        (TelegramForbiddenError, "bot is not an administrator of the chat", "can_restrict_members"),
    ],
)
async def test_permanent_restore_error_stops_and_caches_missing_rights(
    monkeypatch, error_cls, message, permission, caplog
):
    error = error_cls(method=MagicMock(), message=message)
    bot = MagicMock(restrict_chat_member=AsyncMock(side_effect=error))
    publish = AsyncMock()
    record_missing = AsyncMock()
    monkeypatch.setattr("app.core.safe_telegram.broker.publish", publish)
    monkeypatch.setattr("app.core.safe_telegram.permissions.record_missing", record_missing)

    assert await restore_captcha_permissions(bot, -100, 42, 10) is False

    publish.assert_not_awaited()
    if permission:
        record_missing.assert_awaited_once_with(-100, permission)
    else:
        record_missing.assert_not_awaited()
    assert "Cannot restore permissions" in caplog.text


async def test_unexpected_restore_error_is_not_retried(monkeypatch):
    bot = MagicMock(restrict_chat_member=AsyncMock(side_effect=RuntimeError("Unexpected failure")))
    publish = AsyncMock()
    monkeypatch.setattr("app.core.safe_telegram.broker.publish", publish)

    assert await restore_captcha_permissions(bot, -100, 42, 10) is False

    publish.assert_not_awaited()
