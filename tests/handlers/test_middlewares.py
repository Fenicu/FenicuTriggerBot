"""Tests for bot middlewares — each middleware's __call__ method."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Update, Message, User, Chat


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_user(user_id: int = 42, is_bot: bool = False, username: str = "testuser") -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id
    user.is_bot = is_bot
    user.username = username
    user.first_name = "Test"
    user.last_name = "User"
    user.full_name = "Test User"
    user.language_code = "ru"
    user.is_premium = False
    user.mention_html.return_value = "<b>Test User</b>"
    return user


def _make_chat(chat_id: int = -1001000000000, chat_type: str = "supergroup", title: str = "Test Chat") -> MagicMock:
    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    chat.type = chat_type
    chat.title = title
    chat.username = None
    chat.description = None
    chat.invite_link = None
    chat.photo = None
    return chat


def _make_message(
    user: MagicMock | None = None,
    chat: MagicMock | None = None,
    message_id: int = 1,
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = user or _make_user()
    msg.chat = chat or _make_chat()
    msg.message_id = message_id
    msg.new_chat_members = None
    msg.reply_to_message = None
    return msg


def _make_update(
    message: MagicMock | None = None,
    callback_query: MagicMock | None = None,
    my_chat_member: MagicMock | None = None,
    chat_member: MagicMock | None = None,
    event_type: str = "message",
) -> MagicMock:
    update = MagicMock(spec=Update)
    update.message = message
    update.callback_query = callback_query
    update.my_chat_member = my_chat_member
    update.chat_member = chat_member
    update.event_type = event_type

    actual_event = message or callback_query or my_chat_member
    if actual_event and event_type:
        setattr(update, event_type, actual_event)
    return update


# ══════════════════════════════════════════════════════════════════════════════
# IgnoreMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestIgnoreMiddleware:
    """Tests for IgnoreMiddleware — filters bots and system accounts."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.ignore import IgnoreMiddleware

        return IgnoreMiddleware()

    async def test_passes_normal_user(self, middleware):
        user = _make_user(user_id=100, is_bot=False)
        msg = _make_message(user=user)
        event = _make_update(message=msg, event_type="message")
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_blocks_telegram_system_account(self, middleware):
        user = _make_user(user_id=777000)
        msg = _make_message(user=user)
        event = _make_update(message=msg, event_type="message")
        handler = AsyncMock()

        result = await middleware(handler, event, {})

        handler.assert_not_awaited()
        assert result is None

    async def test_blocks_regular_bot(self, middleware):
        user = _make_user(user_id=555, is_bot=True)
        msg = _make_message(user=user)
        event = _make_update(message=msg, event_type="message")
        handler = AsyncMock()

        result = await middleware(handler, event, {})

        handler.assert_not_awaited()
        assert result is None

    async def test_allows_group_anonymous_bot(self, middleware):
        """GroupAnonymousBot (1087968824) should pass through."""
        user = _make_user(user_id=1087968824, is_bot=True)
        msg = _make_message(user=user)
        event = _make_update(message=msg, event_type="message")
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_blocks_bot_in_new_chat_members(self, middleware):
        """If new_chat_members contains a bot, block."""
        bot_member = MagicMock()
        bot_member.is_bot = True
        msg = _make_message()
        msg.new_chat_members = [bot_member]
        event = _make_update(message=msg, event_type="message")
        handler = AsyncMock()

        result = await middleware(handler, event, {})

        handler.assert_not_awaited()
        assert result is None

    async def test_passes_when_no_user(self, middleware):
        """Events with no user (and no event_from_user in data) should pass."""
        event = MagicMock(spec=Update)
        event.event_type = None
        event.chat_member = None
        event.message = None
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# DatabaseMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestDatabaseMiddleware:
    """Tests for DatabaseMiddleware — injects session into data."""

    async def test_injects_session(self):
        mock_session = AsyncMock()
        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("app.bot.middlewares.database.async_session_factory", return_value=mock_factory):
            from app.bot.middlewares.database import DatabaseMiddleware

            middleware = DatabaseMiddleware()
            event = MagicMock()
            data: dict = {}
            handler = AsyncMock(return_value="ok")

            result = await middleware(handler, event, data)

        handler.assert_awaited_once()
        assert result == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# BannedChatMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestBannedChatMiddleware:
    """Tests for BannedChatMiddleware — blocks events from banned chats."""

    @pytest.fixture
    def mock_bot_instance(self):
        bot = MagicMock()
        bot.leave_chat = AsyncMock()
        return bot

    async def test_passes_when_no_chat_id(self, mock_bot_instance):
        from app.bot.middlewares.banned import BannedChatMiddleware

        middleware = BannedChatMiddleware(bot=mock_bot_instance)
        event = MagicMock(spec=Update)
        event.message = None
        event.callback_query = None
        event.my_chat_member = None
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_blocks_cached_banned_chat(self, mock_bot_instance):
        from app.bot.middlewares.banned import BannedChatMiddleware

        middleware = BannedChatMiddleware(bot=mock_bot_instance)
        msg = _make_message()
        event = MagicMock(spec=Update)
        event.message = msg
        event.callback_query = None
        event.my_chat_member = None
        handler = AsyncMock()

        with patch("app.bot.middlewares.banned.valkey") as mock_valkey:
            mock_valkey.get = AsyncMock(return_value="1")
            result = await middleware(handler, event, {})

        handler.assert_not_awaited()
        assert result is None

    async def test_passes_non_banned_chat(self, mock_bot_instance):
        from app.bot.middlewares.banned import BannedChatMiddleware

        middleware = BannedChatMiddleware(bot=mock_bot_instance)
        msg = _make_message()
        event = MagicMock(spec=Update)
        event.message = msg
        event.callback_query = None
        event.my_chat_member = None
        handler = AsyncMock(return_value="ok")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.bot.middlewares.banned.valkey") as mock_valkey:
            mock_valkey.get = AsyncMock(return_value=None)
            result = await middleware(handler, event, {"session": mock_session})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_blocks_db_banned_chat_and_caches(self, mock_bot_instance):
        from app.bot.middlewares.banned import BannedChatMiddleware

        middleware = BannedChatMiddleware(bot=mock_bot_instance)
        msg = _make_message()
        event = MagicMock(spec=Update)
        event.message = msg
        event.callback_query = None
        event.my_chat_member = None
        handler = AsyncMock()

        banned_record = MagicMock()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = banned_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.bot.middlewares.banned.valkey") as mock_valkey:
            mock_valkey.get = AsyncMock(return_value=None)
            mock_valkey.set = AsyncMock()
            result = await middleware(handler, event, {"session": mock_session})

        handler.assert_not_awaited()
        assert result is None
        mock_valkey.set.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# GbanMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestGbanMiddleware:
    """Tests for GbanMiddleware — warns about globally banned users."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.gban import GbanMiddleware

        return GbanMiddleware()

    async def test_passes_non_message_events(self, middleware):
        event = MagicMock()  # Not a Message instance
        # isinstance check will fail for non-Message
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_passes_private_chat(self, middleware):
        chat = _make_chat(chat_type="private")
        msg = _make_message(chat=chat)
        # Make isinstance(event, Message) return True
        handler = AsyncMock(return_value="ok")

        with patch(
            "app.bot.middlewares.gban.isinstance", side_effect=lambda o, t: t is Message or type(o) is type(msg)
        ):
            result = await middleware(handler, msg, {})

        handler.assert_awaited_once()

    async def test_passes_when_gban_disabled(self, middleware):
        """Should pass when db_chat.gban_enabled is False."""
        msg = MagicMock(spec=Message)
        msg.chat = _make_chat(chat_type="supergroup")
        msg.from_user = _make_user()
        msg.new_chat_members = None

        db_chat = MagicMock()
        db_chat.gban_enabled = False
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, msg, {"db_chat": db_chat})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_passes_when_user_not_banned(self, middleware):
        msg = MagicMock(spec=Message)
        msg.chat = _make_chat(chat_type="supergroup")
        msg.from_user = _make_user(user_id=100)
        msg.new_chat_members = None

        db_chat = MagicMock()
        db_chat.gban_enabled = True
        handler = AsyncMock(return_value="ok")

        with patch("app.bot.middlewares.gban.GbanService") as mock_svc:
            mock_svc.is_banned = AsyncMock(return_value=False)
            result = await middleware(handler, msg, {"db_chat": db_chat})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_warns_banned_user_and_still_calls_handler(self, middleware):
        msg = MagicMock(spec=Message)
        msg.chat = _make_chat(chat_type="group")
        msg.from_user = _make_user(user_id=999)
        msg.new_chat_members = None
        msg.reply = AsyncMock()

        db_chat = MagicMock()
        db_chat.gban_enabled = True

        i18n = MagicMock()
        i18n.gban.user.warning.return_value = "You are globally banned"
        i18n.btn.close.return_value = "Close"

        handler = AsyncMock(return_value="ok")

        with patch("app.bot.middlewares.gban.GbanService") as mock_svc:
            mock_svc.is_banned = AsyncMock(return_value=True)
            result = await middleware(handler, msg, {"db_chat": db_chat, "i18n": i18n})

        msg.reply.assert_awaited_once()
        handler.assert_awaited_once()
        assert result == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# I18nMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestI18nMiddleware:
    """Tests for I18nMiddleware — sets i18n translator in data."""

    @pytest.fixture
    def mock_hub(self):
        hub = MagicMock()
        translator = MagicMock()
        hub.get_translator_by_locale.return_value = translator
        return hub

    @pytest.fixture
    def mock_redis(self):
        r = AsyncMock()
        r.get = AsyncMock(return_value=None)
        r.set = AsyncMock()
        return r

    async def test_sets_i18n_from_cached_lang(self, mock_hub, mock_redis):
        from app.bot.middlewares.i18n import I18nMiddleware

        middleware = I18nMiddleware(translator_hub=mock_hub, valkey=mock_redis)
        mock_redis.get = AsyncMock(return_value="en")

        msg = _make_message()
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, msg, {})

        mock_hub.get_translator_by_locale.assert_called_once_with("en")
        handler.assert_awaited_once()
        assert result == "ok"

    async def test_falls_back_to_root_locale_when_no_chat(self, mock_hub, mock_redis):
        from app.bot.middlewares.i18n import I18nMiddleware

        middleware = I18nMiddleware(translator_hub=mock_hub, valkey=mock_redis)
        event = MagicMock()
        event.chat = None
        event.message = None
        event.from_user = None
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()
        assert result == "ok"
        mock_hub.get_translator_by_locale.assert_called_once()

    async def test_queries_db_when_not_cached(self, mock_hub, mock_redis):
        from app.bot.middlewares.i18n import I18nMiddleware

        middleware = I18nMiddleware(translator_hub=mock_hub, valkey=mock_redis)
        mock_redis.get = AsyncMock(return_value=None)

        msg = _make_message()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "uk"
        mock_session.execute = AsyncMock(return_value=mock_result)

        handler = AsyncMock(return_value="ok")
        data = {"session": mock_session}

        result = await middleware(handler, msg, data)

        handler.assert_awaited_once()
        # Should cache the result
        mock_redis.set.assert_awaited_once()
        mock_hub.get_translator_by_locale.assert_called_once_with("uk")


# ══════════════════════════════════════════════════════════════════════════════
# ChatMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestChatMiddleware:
    """Tests for ChatMiddleware — registers/updates chat in DB."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.chat import ChatMiddleware

        return ChatMiddleware()

    async def test_sets_db_chat_in_data(self, middleware):
        db_chat = MagicMock()
        msg = _make_message()
        event = _make_update(message=msg, event_type="message")
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        with patch("app.bot.middlewares.chat.get_or_create_chat", new_callable=AsyncMock, return_value=db_chat):
            data = {"session": session}
            result = await middleware(handler, event, data)

        assert data["db_chat"] is db_chat
        handler.assert_awaited_once()
        assert result == "ok"

    async def test_passes_without_session(self, middleware):
        msg = _make_message()
        event = _make_update(message=msg, event_type="message")
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_passes_without_chat(self, middleware):
        event = MagicMock(spec=Update)
        event.event_type = None
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# UserMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestUserMiddleware:
    """Tests for UserMiddleware — registers/updates user in DB."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.user import UserMiddleware

        return UserMiddleware()

    async def test_sets_user_in_data(self, middleware):
        db_user = MagicMock()
        user = _make_user()
        msg = _make_message(user=user)
        event = _make_update(message=msg, event_type="message")
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        with patch("app.bot.middlewares.user.get_or_create_user", new_callable=AsyncMock, return_value=db_user):
            data = {"session": session}
            result = await middleware(handler, event, data)

        assert data["user"] is db_user
        handler.assert_awaited_once()

    async def test_passes_without_user(self, middleware):
        event = MagicMock(spec=Update)
        event.event_type = None
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {"session": AsyncMock()})

        handler.assert_awaited_once()

    async def test_passes_without_session(self, middleware):
        user = _make_user()
        msg = _make_message(user=user)
        event = _make_update(message=msg, event_type="message")
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# UserChatMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestUserChatMiddleware:
    """Tests for UserChatMiddleware — upserts user-chat link."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.user_chat import UserChatMiddleware

        return UserChatMiddleware()

    async def test_upserts_in_group(self, middleware):
        db_user = MagicMock()
        db_user.id = 42
        db_chat = MagicMock()
        db_chat.id = -100
        db_chat.type = "supergroup"
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        data = {"user": db_user, "db_chat": db_chat, "session": session}
        result = await middleware(handler, MagicMock(), data)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        handler.assert_awaited_once()
        assert result == "ok"

    async def test_skips_private_chat(self, middleware):
        db_user = MagicMock()
        db_chat = MagicMock()
        db_chat.type = "private"
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        data = {"user": db_user, "db_chat": db_chat, "session": session}
        result = await middleware(handler, MagicMock(), data)

        session.execute.assert_not_awaited()
        handler.assert_awaited_once()

    async def test_skips_when_no_user(self, middleware):
        handler = AsyncMock(return_value="ok")
        data = {"db_chat": MagicMock(), "session": AsyncMock()}

        result = await middleware(handler, MagicMock(), data)

        handler.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# StatsMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestStatsMiddleware:
    """Tests for StatsMiddleware — collects daily message stats."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.stats import StatsMiddleware

        return StatsMiddleware()

    async def test_records_stat_for_message(self, middleware):
        msg = MagicMock(spec=Message)
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, msg, {"session": session})

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        handler.assert_awaited_once()
        assert result == "ok"

    async def test_skips_stat_for_non_message(self, middleware):
        event = MagicMock()  # Not a Message instance
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {"session": session})

        session.execute.assert_not_awaited()
        handler.assert_awaited_once()
        assert result == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# TrustMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestTrustMiddleware:
    """Tests for TrustMiddleware — grants chat trust from trusted users."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.trust import TrustMiddleware

        return TrustMiddleware()

    async def test_passes_non_message(self, middleware):
        event = MagicMock()  # Not a Message instance
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {"session": AsyncMock()})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_passes_when_no_from_user(self, middleware):
        msg = MagicMock(spec=Message)
        msg.from_user = None
        msg.chat = _make_chat()
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, msg, {"session": AsyncMock()})

        handler.assert_awaited_once()

    async def test_grants_trust_from_trusted_user(self, middleware):
        user = _make_user()
        msg = MagicMock(spec=Message)
        msg.from_user = user
        msg.chat = _make_chat(chat_type="supergroup")
        msg.answer = AsyncMock()

        db_user = MagicMock()
        db_user.is_trusted = True
        db_chat = MagicMock()
        db_chat.is_trusted = False
        session = AsyncMock()
        i18n = MagicMock()
        i18n.chat.became.trusted.return_value = "Chat is now trusted!"

        handler = AsyncMock(return_value="ok")
        data = {"session": session, "user": db_user, "db_chat": db_chat, "i18n": i18n}

        result = await middleware(handler, msg, data)

        assert db_chat.is_trusted is True
        session.commit.assert_awaited_once()
        msg.answer.assert_awaited_once()
        handler.assert_awaited_once()

    async def test_no_grant_when_chat_already_trusted(self, middleware):
        user = _make_user()
        msg = MagicMock(spec=Message)
        msg.from_user = user
        msg.chat = _make_chat(chat_type="supergroup")

        db_user = MagicMock()
        db_user.is_trusted = True
        db_chat = MagicMock()
        db_chat.is_trusted = True  # Already trusted
        session = AsyncMock()

        handler = AsyncMock(return_value="ok")
        data = {"session": session, "user": db_user, "db_chat": db_chat}

        result = await middleware(handler, msg, data)

        session.commit.assert_not_awaited()
        handler.assert_awaited_once()

    async def test_no_grant_when_user_not_trusted(self, middleware):
        user = _make_user()
        msg = MagicMock(spec=Message)
        msg.from_user = user
        msg.chat = _make_chat(chat_type="supergroup")

        db_user = MagicMock()
        db_user.is_trusted = False
        db_chat = MagicMock()
        db_chat.is_trusted = False
        session = AsyncMock()

        handler = AsyncMock(return_value="ok")
        data = {"session": session, "user": db_user, "db_chat": db_chat}

        result = await middleware(handler, msg, data)

        session.commit.assert_not_awaited()
        handler.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# ReputationMiddleware
# ══════════════════════════════════════════════════════════════════════════════


class TestReputationMiddleware:
    """Tests for ReputationMiddleware — awards reputation points."""

    @pytest.fixture
    def middleware(self):
        from app.bot.middlewares.reputation import ReputationMiddleware

        return ReputationMiddleware()

    async def test_passes_non_message(self, middleware):
        event = MagicMock()  # Not a Message instance
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, event, {})

        handler.assert_awaited_once()
        assert result == "ok"

    async def test_skips_when_tags_disabled(self, middleware):
        msg = MagicMock(spec=Message)
        msg.from_user = _make_user()
        db_chat = MagicMock()
        db_chat.tags_enabled = False
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, msg, {"db_chat": db_chat, "session": session})

        handler.assert_awaited_once()

    async def test_skips_private_chat(self, middleware):
        msg = MagicMock(spec=Message)
        msg.from_user = _make_user()
        db_chat = MagicMock()
        db_chat.tags_enabled = True
        db_chat.type = "private"
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, msg, {"db_chat": db_chat, "session": session})

        handler.assert_awaited_once()

    async def test_awards_message_score(self, middleware):
        user = _make_user(user_id=42, is_bot=False)
        msg = MagicMock(spec=Message)
        msg.from_user = user
        msg.reply_to_message = None
        msg.message_id = 123

        db_chat = MagicMock()
        db_chat.tags_enabled = True
        db_chat.type = "supergroup"
        db_chat.id = -100

        user_chat = MagicMock()
        session = AsyncMock()
        session.get = AsyncMock(return_value=user_chat)
        handler = AsyncMock(return_value="ok")

        with (
            patch("app.bot.middlewares.reputation.add_message_score", new_callable=AsyncMock, return_value=None),
            patch("app.bot.middlewares.reputation.valkey") as mock_valkey,
        ):
            mock_valkey.set = AsyncMock()
            data = {"db_chat": db_chat, "session": session}
            result = await middleware(handler, msg, data)

        handler.assert_awaited_once()
        assert result == "ok"
        session.commit.assert_awaited_once()

    async def test_skips_bot_user(self, middleware):
        user = _make_user(user_id=42, is_bot=True)
        msg = MagicMock(spec=Message)
        msg.from_user = user

        db_chat = MagicMock()
        db_chat.tags_enabled = True
        db_chat.type = "supergroup"
        session = AsyncMock()
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, msg, {"db_chat": db_chat, "session": session})

        handler.assert_awaited_once()
