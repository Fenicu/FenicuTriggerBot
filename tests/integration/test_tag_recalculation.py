"""Tests for app/services/tag_recalculation.py — tag recalculation logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.services.tag_recalculation import (
    _BASE_DELAY,
    _DEACTIVATE_MESSAGES,
    _MAX_RETRIES,
    _SKIP_MESSAGES,
    _set_tag_with_retry,
    _should_deactivate,
    _should_skip,
    recalculate_chat_tags,
)


# ── Helper predicates ────────────────────────────────────────────────────────


class TestShouldDeactivate:
    def test_matches_deactivate_messages(self):
        assert _should_deactivate("USER_NOT_PARTICIPANT") is True
        assert _should_deactivate("PARTICIPANT_ID_INVALID") is True
        assert _should_deactivate("user is deactivated") is True

    def test_rejects_unrelated_messages(self):
        assert _should_deactivate("Some other error") is False
        assert _should_deactivate("") is False


class TestShouldSkip:
    def test_matches_skip_messages(self):
        assert _should_skip("CHAT_CREATOR_REQUIRED") is True

    def test_rejects_unrelated_messages(self):
        assert _should_skip("USER_NOT_PARTICIPANT") is False
        assert _should_skip("") is False


# ── _set_tag_with_retry ──────────────────────────────────────────────────────


class TestSetTagWithRetry:
    @pytest.fixture
    def user_chat(self):
        uc = MagicMock()
        uc.user_id = 42
        return uc

    async def test_success_on_first_try(self, user_chat):
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            mock_bot.return_value = True
            result = await _set_tag_with_retry(chat_id=-100, user_chat=user_chat, tag="Expert")

        assert result is True

    async def test_deactivate_on_forbidden_error(self, user_chat):
        exc = TelegramForbiddenError(
            method=MagicMock(),
            message="Forbidden: user is deactivated",
        )
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            mock_bot.side_effect = exc
            result = await _set_tag_with_retry(-100, user_chat, "Expert")

        assert result is None  # Should deactivate

    async def test_skip_on_creator_error(self, user_chat):
        exc = TelegramBadRequest(
            method=MagicMock(),
            message="Bad Request: CHAT_CREATOR_REQUIRED",
        )
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            mock_bot.side_effect = exc
            result = await _set_tag_with_retry(-100, user_chat, "Expert")

        assert result is False

    async def test_deactivate_on_bad_request_participant_invalid(self, user_chat):
        exc = TelegramBadRequest(
            method=MagicMock(),
            message="Bad Request: PARTICIPANT_ID_INVALID",
        )
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            mock_bot.side_effect = exc
            result = await _set_tag_with_retry(-100, user_chat, "Expert")

        assert result is None

    async def test_retry_on_flood_control(self, user_chat):
        flood_exc = TelegramRetryAfter(
            method=MagicMock(),
            message="Flood control exceeded",
            retry_after=1,
        )
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            # Fail twice with rate limit, succeed on third try
            mock_bot.side_effect = [flood_exc, flood_exc, True]
            with patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock):
                result = await _set_tag_with_retry(-100, user_chat, "Expert")

        assert result is True
        assert mock_bot.await_count == 3

    async def test_exhausted_retries_on_flood(self, user_chat):
        flood_exc = TelegramRetryAfter(
            method=MagicMock(),
            message="Flood control exceeded",
            retry_after=1,
        )
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            # Always fail
            mock_bot.side_effect = flood_exc
            with patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock):
                result = await _set_tag_with_retry(-100, user_chat, "Expert")

        assert result is False

    async def test_unexpected_error_returns_false(self, user_chat):
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            mock_bot.side_effect = RuntimeError("Something unexpected")
            result = await _set_tag_with_retry(-100, user_chat, "Expert")

        assert result is False

    async def test_forbidden_non_deactivate_returns_false(self, user_chat):
        exc = TelegramForbiddenError(
            method=MagicMock(),
            message="Forbidden: bot is not a member",
        )
        with patch("app.services.tag_recalculation.bot", new_callable=AsyncMock) as mock_bot:
            mock_bot.side_effect = exc
            result = await _set_tag_with_retry(-100, user_chat, "Expert")

        assert result is False


# ── recalculate_chat_tags ────────────────────────────────────────────────────


class TestRecalculateChatTags:
    async def test_skips_when_chat_not_found(self):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.tag_recalculation.async_session", return_value=mock_factory):
            await recalculate_chat_tags(chat_id=-100)

        # Should not attempt any queries beyond get
        mock_session.execute.assert_not_awaited()

    async def test_skips_when_tags_disabled(self):
        chat = MagicMock()
        chat.tags_enabled = False

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=chat)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.tag_recalculation.async_session", return_value=mock_factory):
            await recalculate_chat_tags(chat_id=-100)

        mock_session.execute.assert_not_awaited()

    async def test_skips_manual_tags(self):
        """User chats with tag_is_manual should be skipped."""
        chat = MagicMock()
        chat.tags_enabled = True

        user_chat = MagicMock()
        user_chat.tag_is_manual = True
        user_chat.reputation_score = 100

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user_chat]

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=chat)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.tag_recalculation.async_session", return_value=mock_factory),
            patch("app.services.tag_recalculation.get_thresholds", return_value=[50, 200, 500, 1500, 5000]),
            patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
        ):
            await recalculate_chat_tags(chat_id=-100)

        # Should commit but not call _set_tag_with_retry
        mock_session.commit.assert_awaited_once()

    async def test_updates_changed_tags(self):
        """Tags that changed should be updated via Telegram API."""
        chat = MagicMock()
        chat.tags_enabled = True

        user_chat = MagicMock()
        user_chat.tag_is_manual = False
        user_chat.reputation_score = 250
        user_chat.reputation_level = 1
        user_chat.tag = "Member"
        user_chat.user_id = 42
        user_chat.is_active = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user_chat]

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=chat)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.tag_recalculation.async_session", return_value=mock_factory),
            patch("app.services.tag_recalculation.get_thresholds", return_value=[50, 200, 500, 1500, 5000]),
            patch("app.services.tag_recalculation.calculate_level", return_value=2),
            patch("app.services.tag_recalculation.get_level_name", return_value="Active"),
            patch("app.services.tag_recalculation._set_tag_with_retry", new_callable=AsyncMock, return_value=True),
            patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
        ):
            await recalculate_chat_tags(chat_id=-100)

        assert user_chat.reputation_level == 2
        assert user_chat.tag == "Active"
        mock_session.commit.assert_awaited_once()

    async def test_deactivates_invalid_user(self):
        """When _set_tag_with_retry returns None, user should be deactivated."""
        chat = MagicMock()
        chat.tags_enabled = True

        user_chat = MagicMock()
        user_chat.tag_is_manual = False
        user_chat.reputation_score = 100
        user_chat.reputation_level = 0
        user_chat.tag = None
        user_chat.user_id = 42
        user_chat.is_active = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user_chat]

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=chat)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.tag_recalculation.async_session", return_value=mock_factory),
            patch("app.services.tag_recalculation.get_thresholds", return_value=[50, 200, 500, 1500, 5000]),
            patch("app.services.tag_recalculation.calculate_level", return_value=1),
            patch("app.services.tag_recalculation.get_level_name", return_value="Member"),
            patch("app.services.tag_recalculation._set_tag_with_retry", new_callable=AsyncMock, return_value=None),
            patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
        ):
            await recalculate_chat_tags(chat_id=-100)

        assert user_chat.is_active is False
        mock_session.commit.assert_awaited_once()

    async def test_skips_unchanged_tags(self):
        """Tags that haven't changed should not trigger API calls."""
        chat = MagicMock()
        chat.tags_enabled = True

        user_chat = MagicMock()
        user_chat.tag_is_manual = False
        user_chat.reputation_score = 100
        user_chat.reputation_level = 1
        user_chat.tag = "Member"
        user_chat.user_id = 42

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user_chat]

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=chat)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.tag_recalculation.async_session", return_value=mock_factory),
            patch("app.services.tag_recalculation.get_thresholds", return_value=[50, 200, 500, 1500, 5000]),
            patch("app.services.tag_recalculation.calculate_level", return_value=1),
            patch("app.services.tag_recalculation.get_level_name", return_value="Member"),
            patch("app.services.tag_recalculation._set_tag_with_retry", new_callable=AsyncMock) as mock_retry,
            patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
        ):
            await recalculate_chat_tags(chat_id=-100)

        mock_retry.assert_not_awaited()
