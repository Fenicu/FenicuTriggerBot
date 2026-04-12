"""Tests for app/core/config.py — computed fields and validators."""

import os

import pytest


# ---------------------------------------------------------------------------
# BOT_ADMINS computed field
# ---------------------------------------------------------------------------


class TestBotAdmins:
    """Test the BOT_ADMINS computed field that parses BOT_ADMINS_STR."""

    def _make_settings(self, admins_str: str):
        """Create a Settings instance with the given BOT_ADMINS string."""
        from app.core.config import Settings

        env = {
            "POSTGRES_URL": "postgresql+asyncpg://u:p@localhost/db",
            "VALKEY_URL": "redis://localhost:6379/0",
            "BOT_TOKEN": "000:AAA",
            "WEBAPP_URL": "http://localhost",
            "WEBHOOK_URL": "http://localhost/webhook",
            "WEBHOOK_PATH": "/webhook",
            "SECRET_TOKEN": "secret",
            "S3_ACCESS_KEY": "key",
            "S3_SECRET_KEY": "secret",
            "MODERATION_CHANNEL_ID": "-1001234567890",
            "BOT_ADMINS": admins_str,
            "SESSION_SECRET_KEY": "session-secret-key-at-least-32chars!",
        }
        return Settings(**env)

    def test_single_admin(self):
        s = self._make_settings("12345")
        assert s.BOT_ADMINS == [12345]

    def test_multiple_admins(self):
        s = self._make_settings("111,222,333")
        assert s.BOT_ADMINS == [111, 222, 333]

    def test_admins_with_spaces(self):
        s = self._make_settings(" 111 , 222 , 333 ")
        assert s.BOT_ADMINS == [111, 222, 333]

    def test_empty_string(self):
        s = self._make_settings("")
        assert s.BOT_ADMINS == []

    def test_invalid_value_returns_empty(self):
        s = self._make_settings("abc,def")
        assert s.BOT_ADMINS == []

    def test_mixed_valid_invalid_returns_empty(self):
        # Since int() conversion fails for the whole list, returns []
        s = self._make_settings("123,abc")
        assert s.BOT_ADMINS == []

    def test_trailing_comma(self):
        s = self._make_settings("111,222,")
        assert s.BOT_ADMINS == [111, 222]

    def test_leading_comma(self):
        s = self._make_settings(",111,222")
        assert s.BOT_ADMINS == [111, 222]


# ---------------------------------------------------------------------------
# validate_timezone
# ---------------------------------------------------------------------------


class TestValidateTimezone:
    def _make_settings(self, tz: str):
        from app.core.config import Settings

        env = {
            "POSTGRES_URL": "postgresql+asyncpg://u:p@localhost/db",
            "VALKEY_URL": "redis://localhost:6379/0",
            "BOT_TOKEN": "000:AAA",
            "WEBAPP_URL": "http://localhost",
            "WEBHOOK_URL": "http://localhost/webhook",
            "WEBHOOK_PATH": "/webhook",
            "SECRET_TOKEN": "secret",
            "S3_ACCESS_KEY": "key",
            "S3_SECRET_KEY": "secret",
            "MODERATION_CHANNEL_ID": "-1001234567890",
            "BOT_TIMEZONE": tz,
            "SESSION_SECRET_KEY": "session-secret-key-at-least-32chars!",
        }
        return Settings(**env)

    def test_valid_timezone_moscow(self):
        s = self._make_settings("Europe/Moscow")
        assert s.BOT_TIMEZONE == "Europe/Moscow"

    def test_valid_timezone_utc(self):
        s = self._make_settings("UTC")
        assert s.BOT_TIMEZONE == "UTC"

    def test_valid_timezone_us(self):
        s = self._make_settings("America/New_York")
        assert s.BOT_TIMEZONE == "America/New_York"

    def test_invalid_timezone_raises(self):
        with pytest.raises(Exception):
            self._make_settings("Not/A/Timezone")

    def test_empty_timezone_raises(self):
        with pytest.raises(Exception):
            self._make_settings("")

    def test_valid_timezone_asia(self):
        s = self._make_settings("Asia/Tokyo")
        assert s.BOT_TIMEZONE == "Asia/Tokyo"
