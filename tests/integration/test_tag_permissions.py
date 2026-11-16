"""Регрессия: чаты без права на теги больше не получают вызовы setChatMemberTag."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.core.permissions import parse_missing_permission
from app.services.tag_recalculation import recalculate_chat_tags
from app.services.tag_service import TAG_PERMISSION, _set_chat_member_tag, remember_tag_failure


# ── parse_missing_permission ─────────────────────────────────────────────────


def test_parse_tag_permission():
    assert parse_missing_permission("Bad Request: not enough rights to manage tags") == TAG_PERMISSION


@pytest.mark.parametrize("message", ["Bad Request: CHAT_CREATOR_REQUIRED", "Bad Request: CHAT_ADMIN_REQUIRED"])
def test_generic_admin_errors_are_not_tag_permission(message):
    # Эти ошибки приходят и от restrict/ban/delete: глобально к правам на теги их не привязываем
    assert parse_missing_permission(message) != TAG_PERMISSION


@pytest.mark.parametrize("message", ["Bad Request: CHAT_CREATOR_REQUIRED", "Bad Request: CHAT_ADMIN_REQUIRED"])
async def test_remember_tag_failure_maps_admin_errors_to_tags(message):
    error = TelegramBadRequest(method=MagicMock(), message=message)

    with patch("app.services.tag_service.permissions.record_missing", new=AsyncMock()) as record_missing:
        await remember_tag_failure(-100, error)

    record_missing.assert_awaited_once_with(-100, TAG_PERMISSION)


def test_parse_unrelated_message():
    assert parse_missing_permission("Bad Request: message is too long") is None


# ── remember_tag_failure ─────────────────────────────────────────────────────


async def test_remember_tag_failure_records_permission():
    error = TelegramBadRequest(method=MagicMock(), message="Bad Request: CHAT_CREATOR_REQUIRED")

    with patch("app.services.tag_service.permissions") as mock_permissions:
        mock_permissions.parse_missing_permission.return_value = TAG_PERMISSION
        mock_permissions.record_missing = AsyncMock()

        await remember_tag_failure(-100, error)

    mock_permissions.record_missing.assert_awaited_once_with(-100, TAG_PERMISSION)


async def test_remember_tag_failure_ignores_other_errors():
    error = TelegramBadRequest(method=MagicMock(), message="Bad Request: message is too long")

    with patch("app.services.tag_service.permissions") as mock_permissions:
        mock_permissions.parse_missing_permission.return_value = None
        mock_permissions.record_missing = AsyncMock()

        await remember_tag_failure(-100, error)

    mock_permissions.record_missing.assert_not_awaited()


# ── _set_chat_member_tag ─────────────────────────────────────────────────────


async def test_set_tag_skips_when_permission_cached():
    bot = AsyncMock()

    with (
        patch("app.services.tag_service.permissions") as mock_permissions,
        patch("app.services.tag_service.tag_calls_blocked", new_callable=AsyncMock, return_value=True),
    ):
        mock_permissions.record_missing = AsyncMock()
        result = await _set_chat_member_tag(bot, -100, 42, "Member")

    assert result is False
    bot.assert_not_awaited()
    mock_permissions.record_missing.assert_not_awaited()


async def test_set_tag_records_permission_failure():
    bot = AsyncMock()
    bot.side_effect = TelegramBadRequest(method=MagicMock(), message="Bad Request: CHAT_CREATOR_REQUIRED")

    with (
        patch("app.services.tag_service.tag_calls_blocked", new_callable=AsyncMock, return_value=False),
        patch("app.services.tag_service.remember_tag_failure", new_callable=AsyncMock) as mock_remember,
    ):
        result = await _set_chat_member_tag(bot, -100, 42, "Member")

    assert result is False
    mock_remember.assert_awaited_once()


# ── recalculate_chat_tags ────────────────────────────────────────────────────


def _chat():
    chat = MagicMock()
    chat.tags_enabled = True
    chat.tags_preset = "neutral"
    chat.tags_custom = None
    chat.language_code = "ru"
    chat.tags_thresholds = None
    return chat


def _user_chat():
    uc = MagicMock()
    uc.tag_is_manual = False
    uc.reputation_score = 100
    uc.reputation_level = 0
    uc.tag = None
    uc.user_id = 42
    uc.is_active = True
    return uc


def _session(chat, user_chats):
    result = MagicMock()
    result.scalars.return_value.all.return_value = user_chats

    session = AsyncMock()
    session.get = AsyncMock(return_value=chat)
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    factory = AsyncMock()
    factory.__aenter__ = AsyncMock(return_value=session)
    factory.__aexit__ = AsyncMock(return_value=False)
    return factory, session


async def test_recalculation_stops_when_tag_calls_blocked():
    """Если право на теги отсутствует, пересчёт не тратит вызовы API."""
    factory, session = _session(_chat(), [_user_chat()])

    with (
        patch("app.services.tag_recalculation.async_session", return_value=factory),
        patch("app.services.tag_recalculation.tag_calls_blocked", new_callable=AsyncMock, return_value=True),
        patch("app.services.tag_recalculation._set_tag_with_retry", new_callable=AsyncMock) as mock_set,
        patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
    ):
        await recalculate_chat_tags(chat_id=-100)

    mock_set.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("message", ["Bad Request: CHAT_CREATOR_REQUIRED", "Bad Request: CHAT_ADMIN_REQUIRED"])
async def test_recalculation_records_missing_tag_permission(message):
    factory, _ = _session(_chat(), [_user_chat()])
    exc = TelegramBadRequest(method=MagicMock(), message=message)

    with (
        patch("app.services.tag_recalculation.async_session", return_value=factory),
        patch("app.services.tag_recalculation.tag_calls_blocked", new_callable=AsyncMock, return_value=False),
        patch("app.services.tag_recalculation.remember_tag_failure", new_callable=AsyncMock) as mock_remember,
        patch("app.services.tag_recalculation.bot", new_callable=AsyncMock, side_effect=exc),
        patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
    ):
        await recalculate_chat_tags(chat_id=-100)

    mock_remember.assert_awaited_once_with(-100, exc)
