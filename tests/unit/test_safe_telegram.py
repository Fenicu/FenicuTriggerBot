"""Tests for app/core/safe_telegram.handle_send_error."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.core.safe_telegram import handle_send_error, is_topic_error


def _bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message=text)


def _retry_after(seconds: int = 11) -> TelegramRetryAfter:
    return TelegramRetryAfter(method=MagicMock(), message="Flood control", retry_after=seconds)


async def test_retry_after_is_handled():
    handled = await handle_send_error(_retry_after(11), chat_id=-100)
    assert handled is True


async def test_topic_closed_is_handled():
    handled = await handle_send_error(_bad_request("Bad Request: TOPIC_CLOSED"), chat_id=-100)
    assert handled is True


async def test_message_thread_not_found_is_handled():
    handled = await handle_send_error(_bad_request("Bad Request: MESSAGE_THREAD_NOT_FOUND"), chat_id=-100)
    assert handled is True


async def test_chat_write_forbidden_records_permission():
    """CHAT_WRITE_FORBIDDEN — глобальный запрет, должен записаться в кэш can_send_messages,
    иначе pre-check в matching не сработает на следующих апдейтах."""
    exc = _bad_request("Bad Request: CHAT_WRITE_FORBIDDEN")
    with patch("app.core.safe_telegram.permissions.record_missing", new_callable=AsyncMock) as mock_record:
        handled = await handle_send_error(exc, chat_id=-100)

    assert handled is True
    mock_record.assert_awaited_once_with(-100, "can_send_messages")


async def test_not_enough_rights_records_permission():
    exc = _bad_request("Bad Request: not enough rights to send text messages to the chat")
    with patch("app.core.safe_telegram.permissions.record_missing", new_callable=AsyncMock) as mock_record:
        handled = await handle_send_error(exc, chat_id=-100)

    assert handled is True
    mock_record.assert_awaited_once_with(-100, "can_send_messages")


async def test_unknown_bad_request_is_not_handled():
    exc = _bad_request("Bad Request: MESSAGE_TOO_LONG")
    handled = await handle_send_error(exc, chat_id=-100)
    assert handled is False


async def test_unrelated_exception_is_not_handled():
    handled = await handle_send_error(RuntimeError("network down"), chat_id=-100)
    assert handled is False


async def test_forbidden_error_is_not_handled():
    """TelegramForbiddenError handled by caller (chat deactivation), not by this helper."""
    exc = TelegramForbiddenError(method=MagicMock(), message="Forbidden: bot was kicked")
    handled = await handle_send_error(exc, chat_id=-100)
    assert handled is False


def test_is_topic_error_for_topic_closed():
    assert is_topic_error(_bad_request("Bad Request: TOPIC_CLOSED")) is True


def test_is_topic_error_for_message_thread_not_found():
    assert is_topic_error(_bad_request("Bad Request: MESSAGE_THREAD_NOT_FOUND")) is True


def test_is_topic_error_false_for_other_bad_request():
    assert is_topic_error(_bad_request("Bad Request: CHAT_WRITE_FORBIDDEN")) is False


def test_is_topic_error_false_for_non_telegram_exception():
    assert is_topic_error(RuntimeError("boom")) is False
