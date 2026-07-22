"""Тесты эфемерных ответов команд: /status, /warns, /vars, /auditlog + отказы фильтров прав.

Реальный Postgres (`db_session`) и реальный Valkey (кэш прав через `permissions.is_missing`)
из корневого conftest; `bot` подменяется через monkeypatch на уровне модуля-обработчика
(см. tests/handlers/test_captcha_ephemeral.py) -- каждый модуль импортирует его как
`from app.bot.instance import bot`, своя привязка имени, патч канонического модуля её не видит.

Для проверки публичного fallback-пути (когда эфемерная отправка и, для sensitive=True, ЛС
недоступны) подменяется `app.core.safe_telegram.safe_send_message` напрямую -- сами механики
fallback уже исчерпывающе покрыты tests/core/test_ephemeral_answer.py, здесь важно только
что каждый handler передаёт правильные `sensitive`/`fallback_notice`/текст.
"""

from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.bot.filters.moderation import HasBotRights, HasUserRights
from tests.factories import create_chat, create_user, create_warn


# ── Helpers ───────────────────────────────────────────────────────────────────


def _bad_request(text: str = "Bad Request: BOT_NOT_ADMIN") -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message=text)


def _forbidden(text: str = "Forbidden: bot can't initiate conversation with a user") -> TelegramForbiddenError:
    return TelegramForbiddenError(method=MagicMock(), message=text)


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    return bot


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.reputation.group.only.return_value = "Groups only"
    i18n.reputation.disabled.return_value = "Reputation disabled"
    i18n.reputation.no.data.return_value = "No data"
    i18n.reputation.status.return_value = "Status text"
    i18n.reputation.next.level.return_value = "10 until next"
    i18n.reputation.max.level.return_value = "Max level!"
    i18n.warns.none.user.return_value = "No warns for user"
    i18n.mod.warns.list.return_value = "Warns list"
    i18n.error.no.rights.return_value = "No rights"
    i18n.mod.error.no.rights.return_value = "No bot rights"
    i18n.var.list.empty.return_value = "No variables"
    i18n.var.list.header.return_value = "Variables:"
    i18n.ephemeral.fallback.notice.return_value = "Ответ отправлен в личные сообщения"
    return i18n


def _make_message(
    chat_id: int,
    user_id: int,
    *,
    chat_type: str = "supergroup",
    member_status: str = "member",
    reply_user=None,
    ephemeral_message_id: int | None = None,
):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type=chat_type)
    msg.from_user = MagicMock(id=user_id, username="testuser", full_name="Test User")
    msg.ephemeral_message_id = ephemeral_message_id

    member = MagicMock(status=member_status)
    msg.chat.get_member = AsyncMock(return_value=member)

    if reply_user:
        msg.reply_to_message = MagicMock()
        msg.reply_to_message.from_user = reply_user
    else:
        msg.reply_to_message = None

    return msg


def _make_filter_message(
    chat_id: int, user_id: int, *, bot_id: int = 99, bot_status: str = "member", user_status: str = "member"
):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.from_user = MagicMock(id=user_id)
    msg.ephemeral_message_id = None
    msg.bot = MagicMock()
    msg.bot.id = bot_id
    msg.bot.send_message = AsyncMock(return_value=MagicMock())

    async def _get_member(member_id):
        status = bot_status if member_id == bot_id else user_status
        return MagicMock(status=status)

    msg.chat.get_member = AsyncMock(side_effect=_get_member)
    return msg


# ── /status (reputation.py, sensitive=False) ────────────────────────────────────


async def test_status_group_only_direct_send_in_private(db_session, monkeypatch):
    """chat.type не group/supergroup -> ephemeral_answer(sensitive=False); в ЛС -- обычная отправка."""
    from app.bot.handlers.reputation import status_command

    chat = await create_chat(db_session, tags_enabled=True)
    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    msg = _make_message(chat.id, 111, chat_type="private")
    await status_command(msg, db_session, _make_i18n(), chat)

    mock_bot.send_message.assert_awaited_once_with(chat_id=chat.id, text="Groups only", parse_mode="HTML")


async def test_status_disabled_sent_ephemeral_in_group(db_session, monkeypatch):
    """Теги выключены -> ephemeral_answer уходит с receiver_user_id (эфемерно в группе)."""
    from app.bot.handlers.reputation import status_command

    chat = await create_chat(db_session, tags_enabled=False)
    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    msg = _make_message(chat.id, 222)
    await status_command(msg, db_session, _make_i18n(), chat)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "Reputation disabled"
    assert kwargs["receiver_user_id"] == 222


async def test_status_no_data_falls_back_publicly_with_full_text(db_session, monkeypatch):
    """Эфемерная отправка упала -> sensitive=False публикует САМ текст (не notice)."""
    from app.bot.handlers.reputation import status_command

    chat = await create_chat(db_session, tags_enabled=True)
    mock_bot = _make_bot()
    mock_bot.send_message = AsyncMock(side_effect=_bad_request())
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)
    mock_safe_send = AsyncMock(return_value=MagicMock(message_id=999))
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)

    msg = _make_message(chat.id, 333)
    await status_command(msg, db_session, _make_i18n(), chat)

    mock_safe_send.assert_awaited_once()
    _, kwargs = mock_safe_send.call_args
    assert kwargs["text"] == "No data"


async def test_status_success_sent_ephemeral(db_session, monkeypatch):
    """Полный успешный статус -> ephemeral_answer с receiver_user_id."""
    from app.bot.handlers.reputation import status_command
    from app.db.models.user_chat import UserChat

    chat = await create_chat(db_session, tags_enabled=True)
    user = await create_user(db_session)
    db_session.add(UserChat(user_id=user.id, chat_id=chat.id, reputation_score=100, reputation_level=1))
    await db_session.flush()

    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    msg = _make_message(chat.id, user.id)
    await status_command(msg, db_session, _make_i18n(), chat)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "Status text"
    assert kwargs["receiver_user_id"] == user.id


# ── /warns (chat_moderation.py, sensitive=True) ─────────────────────────────────


async def test_warns_self_no_warns_sent_ephemeral(db_session, monkeypatch):
    """Нет варнов -> ephemeral_answer(sensitive=True) уходит с receiver_user_id."""
    from app.bot.handlers.chat_moderation import cmd_warns

    chat = await create_chat(db_session, module_moderation=True)
    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.chat_moderation.bot", mock_bot)

    msg = _make_message(chat.id, 444)
    await cmd_warns(msg, db_session, chat, _make_i18n())

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "No warns for user"
    assert kwargs["receiver_user_id"] == 444


async def test_warns_dm_forbidden_posts_neutral_notice_not_warn_data(db_session, monkeypatch):
    """sensitive=True: эфемерная отправка и ЛС упали -> публично уходит notice, а НЕ список варнов."""
    from app.bot.handlers.chat_moderation import cmd_warns

    chat = await create_chat(db_session, module_moderation=True)
    user = await create_user(db_session)
    await create_warn(db_session, chat.id, user.id, admin_id=user.id, reason="test reason")
    await db_session.commit()

    mock_bot = _make_bot()

    async def _send(*, chat_id, text, **_kwargs):
        raise _forbidden() if chat_id == user.id else _bad_request()

    mock_bot.send_message = AsyncMock(side_effect=_send)
    monkeypatch.setattr("app.bot.handlers.chat_moderation.bot", mock_bot)
    mock_safe_send = AsyncMock(return_value=MagicMock(message_id=999))
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)

    msg = _make_message(chat.id, user.id)
    await cmd_warns(msg, db_session, chat, _make_i18n())

    mock_safe_send.assert_awaited_once()
    _, kwargs = mock_safe_send.call_args
    assert kwargs["text"] == "Ответ отправлен в личные сообщения"


# ── /vars (variables.py, sensitive=True кроме "нет прав") ───────────────────────


async def test_vars_not_admin_ephemeral_sensitive_false(db_session, monkeypatch):
    """Ранний отказ (не админ) -> ephemeral_answer(sensitive=False)."""
    from app.bot.handlers.variables import list_vars_command

    chat = await create_chat(db_session)
    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)

    msg = _make_message(chat.id, 555, member_status="member")
    await list_vars_command(msg, db_session, _make_i18n())

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "No rights"
    assert kwargs["receiver_user_id"] == 555


async def test_vars_with_data_sent_to_dm_when_ephemeral_fails(db_session, monkeypatch):
    """sensitive=True: эфемерная отправка упала, но ЛС прошло -> список переменных ушёл в ЛС."""
    from app.bot.handlers.variables import list_vars_command
    from app.services.chat_variable_service import set_var

    chat = await create_chat(db_session)
    await set_var(db_session, chat.id, "greeting", "Hello")

    mock_bot = _make_bot()
    dm_message = MagicMock()

    async def _send(*, chat_id, text, **_kwargs):
        if chat_id == chat.id:
            raise _bad_request()
        assert chat_id == 666
        return dm_message

    mock_bot.send_message = AsyncMock(side_effect=_send)
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)

    msg = _make_message(chat.id, 666, member_status="administrator")
    await list_vars_command(msg, db_session, _make_i18n())

    assert mock_bot.send_message.await_count == 2
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["chat_id"] == 666
    assert "greeting" in kwargs["text"]


async def test_vars_dm_forbidden_posts_neutral_notice_not_var_data(db_session, monkeypatch):
    """sensitive=True: эфемерная отправка и ЛС упали -> публично уходит notice, а НЕ список переменных."""
    from app.bot.handlers.variables import list_vars_command
    from app.services.chat_variable_service import set_var

    chat = await create_chat(db_session)
    await set_var(db_session, chat.id, "greeting", "Hello")
    user_id = 667

    mock_bot = _make_bot()

    async def _send(*, chat_id, text, **_kwargs):
        raise _forbidden() if chat_id == user_id else _bad_request()

    mock_bot.send_message = AsyncMock(side_effect=_send)
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)
    mock_safe_send = AsyncMock(return_value=MagicMock(message_id=999))
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)

    msg = _make_message(chat.id, user_id, member_status="administrator")
    await list_vars_command(msg, db_session, _make_i18n())

    mock_safe_send.assert_awaited_once()
    _, kwargs = mock_safe_send.call_args
    assert kwargs["text"] == "Ответ отправлен в личные сообщения"
    assert "greeting" not in kwargs["text"]


# ── /auditlog (admin.py, sensitive=True кроме "нет прав") ───────────────────────


async def test_auditlog_not_admin_ephemeral_sensitive_false(db_session, monkeypatch):
    """Ранний отказ (не админ) -> ephemeral_answer(sensitive=False)."""
    from app.bot.handlers.admin import auditlog_command

    chat = await create_chat(db_session)
    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.admin.bot", mock_bot)

    msg = _make_message(chat.id, 777, member_status="member")
    await auditlog_command(msg, db_session, _make_i18n(), chat)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "No rights"
    assert kwargs["receiver_user_id"] == 777


async def test_auditlog_empty_sent_ephemeral(db_session, monkeypatch):
    """Пустая история изменений -> ephemeral_answer(sensitive=True) с receiver_user_id."""
    from app.bot.handlers.admin import auditlog_command

    chat = await create_chat(db_session)
    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.admin.bot", mock_bot)

    msg = _make_message(chat.id, 888, member_status="administrator")
    await auditlog_command(msg, db_session, _make_i18n(), chat)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert "пуста" in kwargs["text"]
    assert kwargs["receiver_user_id"] == 888


async def test_auditlog_entries_sent_to_dm_when_ephemeral_fails(db_session, monkeypatch):
    """sensitive=True: эфемерная отправка упала, ЛС прошло -> история изменений ушла в ЛС."""
    from app.bot.handlers.admin import auditlog_command
    from app.services.audit_service import record_settings_changes

    chat = await create_chat(db_session, module_moderation=False)
    await record_settings_changes(db_session, chat, 42, {"module_moderation": True})
    await db_session.commit()

    mock_bot = _make_bot()
    dm_message = MagicMock()

    async def _send(*, chat_id, text, **_kwargs):
        if chat_id == chat.id:
            raise _bad_request()
        assert chat_id == 999
        return dm_message

    mock_bot.send_message = AsyncMock(side_effect=_send)
    monkeypatch.setattr("app.bot.handlers.admin.bot", mock_bot)

    msg = _make_message(chat.id, 999, member_status="administrator")
    await auditlog_command(msg, db_session, _make_i18n(), chat)

    assert mock_bot.send_message.await_count == 2
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["chat_id"] == 999
    assert "Модерация" in kwargs["text"]


async def test_auditlog_dm_forbidden_posts_neutral_notice_not_audit_data(db_session, monkeypatch):
    """sensitive=True: эфемерная отправка и ЛС упали -> публично уходит notice, а НЕ история изменений."""
    from app.bot.handlers.admin import auditlog_command
    from app.services.audit_service import record_settings_changes

    chat = await create_chat(db_session, module_moderation=False)
    await record_settings_changes(db_session, chat, 42, {"module_moderation": True})
    await db_session.commit()
    user_id = 1000

    mock_bot = _make_bot()

    async def _send(*, chat_id, text, **_kwargs):
        raise _forbidden() if chat_id == user_id else _bad_request()

    mock_bot.send_message = AsyncMock(side_effect=_send)
    monkeypatch.setattr("app.bot.handlers.admin.bot", mock_bot)
    mock_safe_send = AsyncMock(return_value=MagicMock(message_id=999))
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)

    msg = _make_message(chat.id, user_id, member_status="administrator")
    await auditlog_command(msg, db_session, _make_i18n(), chat)

    mock_safe_send.assert_awaited_once()
    _, kwargs = mock_safe_send.call_args
    assert kwargs["text"] == "Ответ отправлен в личные сообщения"
    assert "Модерация" not in kwargs["text"]


# ── Фильтры прав (HasBotRights / HasUserRights) ─────────────────────────────────


async def test_bot_rights_filter_error_ephemeral(db_session):
    """HasBotRights: бот не админ -> отказ уходит через ephemeral_answer(sensitive=False)."""
    chat = await create_chat(db_session)
    msg = _make_filter_message(chat.id, 111, bot_status="member")

    result = await HasBotRights()(msg, _make_i18n())

    assert result is False
    msg.bot.send_message.assert_awaited_once()
    _, kwargs = msg.bot.send_message.call_args
    assert kwargs["text"] == "No bot rights"
    assert kwargs["receiver_user_id"] == 111


async def test_user_rights_filter_error_ephemeral(db_session):
    """HasUserRights: юзер не админ -> отказ уходит через ephemeral_answer(sensitive=False)."""
    chat = await create_chat(db_session)
    msg = _make_filter_message(chat.id, 222, user_status="member")

    result = await HasUserRights()(msg, _make_i18n())

    assert result is False
    msg.bot.send_message.assert_awaited_once()
    _, kwargs = msg.bot.send_message.call_args
    assert kwargs["text"] == "No bot rights"
    assert kwargs["receiver_user_id"] == 222
