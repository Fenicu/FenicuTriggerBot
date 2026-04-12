"""Tests for app/services/captcha_service.py — captcha generation and verification."""

import json

import pytest
from unittest.mock import AsyncMock, patch

from app.services.captcha_service import (
    ALL_EMOJIS,
    STYLES,
    CaptchaData,
    CaptchaResult,
    CaptchaService,
    CaptchaSessionData,
)


@pytest.fixture
def mock_valkey():
    """Patch the module-level valkey used by captcha_service."""
    with patch("app.services.captcha_service.valkey") as m:
        m.get = AsyncMock(return_value=None)
        m.set = AsyncMock()
        m.delete = AsyncMock()
        m.ttl = AsyncMock(return_value=250)
        m.sismember = AsyncMock(return_value=False)
        yield m


# ── Redis key generation ─────────────────────────────────────────────────────


class TestRedisKey:
    def test_key_format(self):
        key = CaptchaService._get_redis_key(chat_id=-100, user_id=42)
        assert key == "captcha:session:-100:42"

    def test_key_uniqueness(self):
        k1 = CaptchaService._get_redis_key(1, 2)
        k2 = CaptchaService._get_redis_key(2, 1)
        assert k1 != k2


# ── Button generation ────────────────────────────────────────────────────────


class TestGenerateCaptchaButtons:
    def test_returns_16_buttons(self):
        target_emoji, target_style, correct_code, buttons = CaptchaService._generate_captcha_buttons()
        # 1 correct + 1 decoy + 14 others = 16
        assert len(buttons) == 16

    def test_target_emoji_in_all_emojis(self):
        target_emoji, _, _, _ = CaptchaService._generate_captcha_buttons()
        assert target_emoji in ALL_EMOJIS

    def test_target_style_is_valid(self):
        _, target_style, _, _ = CaptchaService._generate_captcha_buttons()
        assert target_style in STYLES

    def test_correct_button_has_correct_code(self):
        target_emoji, target_style, correct_code, buttons = CaptchaService._generate_captcha_buttons()
        correct_buttons = [b for b in buttons if b.code == correct_code]
        assert len(correct_buttons) == 1
        assert correct_buttons[0].emoji == target_emoji
        assert correct_buttons[0].style == target_style

    def test_decoy_button_exists(self):
        """Target emoji appears twice — once correct, once decoy (different style)."""
        target_emoji, target_style, correct_code, buttons = CaptchaService._generate_captcha_buttons()
        target_buttons = [b for b in buttons if b.emoji == target_emoji]
        assert len(target_buttons) == 2
        styles = {b.style for b in target_buttons}
        assert len(styles) == 2  # Two different styles

    def test_correct_button_not_first_or_last(self):
        """The correct button should not be at index 0 or 15."""
        for _ in range(20):  # Run multiple times due to randomness
            _, _, correct_code, buttons = CaptchaService._generate_captcha_buttons()
            correct_idx = next(i for i, b in enumerate(buttons) if b.code == correct_code)
            assert correct_idx != 0
            assert correct_idx != 15


# ── Session creation ─────────────────────────────────────────────────────────


class TestCreateSession:
    async def test_creates_session_and_stores_in_redis(self, mock_valkey):
        result = await CaptchaService.create_session(chat_id=-100, user_id=42)

        assert isinstance(result, CaptchaData)
        assert result.target_emoji in ALL_EMOJIS
        assert result.target_style in STYLES
        assert len(result.buttons) == 16
        mock_valkey.set.assert_awaited_once()

    async def test_session_ttl_is_respected(self, mock_valkey):
        await CaptchaService.create_session(chat_id=-100, user_id=42, session_ttl=600)

        call_kwargs = mock_valkey.set.call_args
        assert call_kwargs.kwargs.get("ex") == 600 or call_kwargs[1].get("ex") == 600


# ── Verification ─────────────────────────────────────────────────────────────


class TestVerifyAttempt:
    async def test_success_on_correct_code(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=3,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.verify_attempt(-100, 42, "abc-123")

        assert result == CaptchaResult.SUCCESS
        mock_valkey.delete.assert_awaited_once()

    async def test_fail_when_no_session(self, mock_valkey):
        mock_valkey.get = AsyncMock(return_value=None)

        result = await CaptchaService.verify_attempt(-100, 42, "any-code")

        assert result == CaptchaResult.FAIL

    async def test_retry_on_wrong_code_with_attempts_left(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=3,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.verify_attempt(-100, 42, "wrong-code")

        assert result == CaptchaResult.RETRY
        # Should save updated session with decremented attempts
        mock_valkey.set.assert_awaited_once()
        saved_json = mock_valkey.set.call_args[0][1]
        saved = CaptchaSessionData.model_validate_json(saved_json)
        assert saved.attempts_left == 2

    async def test_fail_on_last_attempt(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=1,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.verify_attempt(-100, 42, "wrong-code")

        assert result == CaptchaResult.FAIL
        mock_valkey.delete.assert_awaited_once()


# ── Regeneration ─────────────────────────────────────────────────────────────


class TestRegenerateSession:
    async def test_returns_none_when_no_session(self, mock_valkey):
        mock_valkey.get = AsyncMock(return_value=None)

        result = await CaptchaService.regenerate_session(-100, 42)

        assert result is None

    async def test_regenerates_with_preserved_attempts(self, mock_valkey):
        old_session = CaptchaSessionData(
            correct_code="old-code",
            target_emoji="🐶",
            attempts_left=1,
        )
        mock_valkey.get = AsyncMock(return_value=old_session.model_dump_json())
        mock_valkey.ttl = AsyncMock(return_value=150)

        result = await CaptchaService.regenerate_session(-100, 42)

        assert isinstance(result, CaptchaData)
        # New session should be saved with old attempts_left
        saved_json = mock_valkey.set.call_args[0][1]
        saved = CaptchaSessionData.model_validate_json(saved_json)
        assert saved.attempts_left == 1

    async def test_regenerate_uses_remaining_ttl(self, mock_valkey):
        old_session = CaptchaSessionData(
            correct_code="old-code",
            target_emoji="🐶",
            attempts_left=2,
        )
        mock_valkey.get = AsyncMock(return_value=old_session.model_dump_json())
        mock_valkey.ttl = AsyncMock(return_value=100)

        await CaptchaService.regenerate_session(-100, 42)

        call_kwargs = mock_valkey.set.call_args
        assert call_kwargs.kwargs.get("ex") == 100 or call_kwargs[1].get("ex") == 100


# ── Get session ──────────────────────────────────────────────────────────────


class TestGetSession:
    async def test_returns_none_when_missing(self, mock_valkey):
        mock_valkey.get = AsyncMock(return_value=None)

        result = await CaptchaService.get_session(-100, 42)

        assert result is None

    async def test_returns_session_data(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=3,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.get_session(-100, 42)

        assert isinstance(result, CaptchaSessionData)
        assert result.correct_code == "abc-123"
        assert result.attempts_left == 3
