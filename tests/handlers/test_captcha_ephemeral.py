"""Тесты эфемерной капчи: отправка (chat_member.py) и жизненный цикл
(captcha.py колбэки, worker/captcha.py таймаут-кик).

Реальный Postgres (`db_session`) + реальный Valkey (кэш прав/CaptchaService)
из корневого conftest; `bot`/`broker` заменяются вручную через monkeypatch,
т.к. импортированы в целевых модулях как `from ... import bot` (свои
привязки имени, патч канонического модуля их не видит).
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select

from app.bot.handlers.captcha import _handle_fail, _handle_retry, _handle_success
from app.bot.handlers.chat_member import on_chat_member_update
from app.core import permissions
from app.db.models.captcha_session import CaptchaSessionStatus, ChatCaptchaSession
from app.services.captcha_service import CaptchaService
from app.worker.captcha import kick_unverified_user
from tests.factories import create_chat, create_user

CHAT_ID = -100777001
USER_ID = 777001
PERM_MISSING_CHAT_ID = -100777099


# ── Helpers ───────────────────────────────────────────────────────────────────


def _bad_request(text: str = "Bad Request: USER_NOT_PARTICIPANT") -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message=text)


def _forbidden(text: str = "Forbidden: BOT_NOT_ADMIN") -> TelegramForbiddenError:
    return TelegramForbiddenError(method=MagicMock(), message=text)


def _make_mock_bot() -> MagicMock:
    """Bot-мок со всеми методами, задействованными в эфемерном жизненном цикле капчи."""
    bot = MagicMock()
    bot.restrict_chat_member = AsyncMock()
    bot.ban_chat_member = AsyncMock()
    bot.unban_chat_member = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=0, ephemeral_message_id=999))
    bot.delete_ephemeral_message = AsyncMock()
    bot.edit_ephemeral_message_text = AsyncMock()
    bot.edit_ephemeral_message_reply_markup = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.get_me = AsyncMock(return_value=MagicMock(username="TriggerTestBot"))
    return bot


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.captcha.success.return_value = "Verified!"
    i18n.captcha.fail.return_value = "Failed"
    i18n.captcha.retry.return_value = "Retry"
    i18n.captcha.color.danger.return_value = "red"
    i18n.captcha.color.success.return_value = "green"
    i18n.captcha.color.primary.return_value = "blue"
    i18n.captcha.emoji.return_value = "Pick the emoji"
    i18n.captcha.verify.return_value = "Verify yourself"
    i18n.btn.verify.return_value = "Verify"
    return i18n


def _make_callback(chat_id: int = CHAT_ID, user_id: int = USER_ID) -> MagicMock:
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.chat = MagicMock(id=chat_id)
    callback.message.delete = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.from_user = MagicMock(id=user_id)
    callback.from_user.mention_html.return_value = f"<a>{user_id}</a>"
    return callback


def _make_join_event(chat_id: int, user_id: int) -> MagicMock:
    """Duck-typed ChatMemberUpdated: юзер входит из left -> member."""
    user = MagicMock()
    user.id = user_id
    user.username = "newbie"
    user.first_name = "New"
    user.last_name = None
    user.language_code = "ru"
    user.is_premium = False
    user.mention_html.return_value = f"<a>{user_id}</a>"

    chat = MagicMock()
    chat.id = chat_id
    chat.title = "Test Chat"
    chat.username = None
    chat.type = "supergroup"
    chat.description = None
    chat.invite_link = None
    chat.photo = None

    new_member = MagicMock(status="member")
    new_member.user = user

    event = MagicMock()
    event.chat = chat
    event.old_chat_member = MagicMock(status="left")
    event.new_chat_member = new_member
    return event


async def _seed_session(
    db_session,
    *,
    chat_id: int = CHAT_ID,
    user_id: int = USER_ID,
    ephemeral_message_id: int | None = None,
    message_id: int | None = None,
    status: CaptchaSessionStatus = CaptchaSessionStatus.PENDING,
    expires_at: datetime | None = None,
) -> ChatCaptchaSession:
    """Создать PENDING-сессию капчи (chat/user должны существовать в БД)."""
    session_obj = ChatCaptchaSession(
        chat_id=chat_id,
        user_id=user_id,
        ephemeral_message_id=ephemeral_message_id,
        message_id=message_id,
        status=status,
        expires_at=expires_at or (datetime.now().astimezone() + timedelta(minutes=5)),
    )
    db_session.add(session_obj)
    await db_session.commit()
    await db_session.refresh(session_obj)
    return session_obj


async def _fetch_session(db_session, chat_id: int = CHAT_ID, user_id: int = USER_ID) -> ChatCaptchaSession | None:
    stmt = select(ChatCaptchaSession).where(
        ChatCaptchaSession.chat_id == chat_id, ChatCaptchaSession.user_id == user_id
    )
    result = await db_session.execute(stmt)
    return result.scalars().first()


# ── chat_member.py: отправка капчи ────────────────────────────────────────────


async def test_emoji_captcha_sent_ephemeral(db_session, monkeypatch):
    """Emoji-капча уходит с receiver_user_id; сессия хранит ephemeral_message_id, message_id пуст."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")

    mock_bot = _make_mock_bot()
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=0, ephemeral_message_id=999))
    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker", mock_broker)

    event = _make_join_event(CHAT_ID, USER_ID)
    await on_chat_member_update(event, db_session, _make_i18n())

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["receiver_user_id"] == USER_ID
    mock_broker.publish.assert_awaited_once()

    session_obj = await _fetch_session(db_session, CHAT_ID, USER_ID)
    assert session_obj is not None
    assert session_obj.ephemeral_message_id == 999
    assert session_obj.message_id is None


async def test_webapp_captcha_sent_ephemeral(db_session, monkeypatch):
    """Webapp-приглашение тоже уходит эфемерно (не только emoji-сетка)."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="webapp")

    mock_bot = _make_mock_bot()
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=0, ephemeral_message_id=1001))
    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker", mock_broker)

    event = _make_join_event(CHAT_ID, USER_ID)
    await on_chat_member_update(event, db_session, _make_i18n())

    mock_bot.get_me.assert_awaited_once()
    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["receiver_user_id"] == USER_ID
    mock_broker.publish.assert_awaited_once()

    session_obj = await _fetch_session(db_session, CHAT_ID, USER_ID)
    assert session_obj is not None
    assert session_obj.ephemeral_message_id == 1001
    assert session_obj.message_id is None


async def test_captcha_send_falls_back_to_public_on_bad_request(db_session, monkeypatch):
    """Эфемерная отправка упала TelegramBadRequest -> публичная отправка, message_id заполнен."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")

    mock_bot = _make_mock_bot()
    mock_bot.send_message = AsyncMock(side_effect=[_bad_request(), MagicMock(message_id=321)])
    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker", mock_broker)

    event = _make_join_event(CHAT_ID, USER_ID)
    await on_chat_member_update(event, db_session, _make_i18n())

    assert mock_bot.send_message.await_count == 2
    mock_broker.publish.assert_awaited_once()

    session_obj = await _fetch_session(db_session, CHAT_ID, USER_ID)
    assert session_obj is not None
    assert session_obj.message_id == 321
    assert session_obj.ephemeral_message_id is None


async def test_captcha_send_skipped_when_permission_cached_missing(db_session, monkeypatch):
    """Закэшированная бесправность (can_send_messages) -> send_message вообще не зовётся."""
    await create_chat(db_session, id=PERM_MISSING_CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    await permissions.record_missing(PERM_MISSING_CHAT_ID, "can_send_messages")

    mock_bot = _make_mock_bot()
    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker", mock_broker)

    try:
        event = _make_join_event(PERM_MISSING_CHAT_ID, USER_ID)
        await on_chat_member_update(event, db_session, _make_i18n())

        mock_bot.send_message.assert_not_awaited()
        mock_broker.publish.assert_not_awaited()

        session_obj = await _fetch_session(db_session, PERM_MISSING_CHAT_ID, USER_ID)
        assert session_obj is not None
        assert session_obj.ephemeral_message_id is None
        assert session_obj.message_id is None
    finally:
        await permissions.clear_for_chat(PERM_MISSING_CHAT_ID)


async def test_captcha_send_falls_back_to_public_on_forbidden(db_session, monkeypatch):
    """Эфемерная отправка упала TelegramForbiddenError -> тот же публичный fallback."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")

    mock_bot = _make_mock_bot()
    mock_bot.send_message = AsyncMock(side_effect=[_forbidden(), MagicMock(message_id=654)])
    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.chat_member.broker", mock_broker)

    event = _make_join_event(CHAT_ID, USER_ID)
    await on_chat_member_update(event, db_session, _make_i18n())

    assert mock_bot.send_message.await_count == 2
    mock_broker.publish.assert_awaited_once()

    session_obj = await _fetch_session(db_session, CHAT_ID, USER_ID)
    assert session_obj is not None
    assert session_obj.message_id == 654
    assert session_obj.ephemeral_message_id is None


# ── captcha.py: _handle_success ────────────────────────────────────────────────


async def test_success_ephemeral_deletes_and_sends_ephemeral_message(db_session, monkeypatch):
    """Ephemeral-сессия: успех удаляет эфемерную капчу и шлёт эфемерный success-текст."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, ephemeral_message_id=4242)

    mock_bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)

    callback = _make_callback()
    await _handle_success(callback, db_session, _make_i18n())

    mock_bot.restrict_chat_member.assert_awaited_once()
    mock_bot.delete_ephemeral_message.assert_awaited_once_with(
        chat_id=CHAT_ID, receiver_user_id=USER_ID, ephemeral_message_id=4242
    )
    callback.message.delete.assert_not_awaited()

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["receiver_user_id"] == USER_ID

    session_obj = await _fetch_session(db_session)
    assert session_obj.status == CaptchaSessionStatus.PASSED


async def test_success_legacy_deletes_via_callback_and_schedules_autodelete(db_session, monkeypatch):
    """Legacy-сессия (message_id): удаление через callback.message.delete(), success публично + autodelete."""
    chat = await create_chat(
        db_session,
        id=CHAT_ID,
        captcha_enabled=True,
        autodelete_settings={"captcha_success": {"enabled": True, "delay": 10}},
    )
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, message_id=123)

    mock_bot = _make_mock_bot()
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=888))
    mock_schedule = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.captcha.schedule_autodelete", mock_schedule)

    callback = _make_callback()
    await _handle_success(callback, db_session, _make_i18n())

    mock_bot.delete_ephemeral_message.assert_not_awaited()
    callback.message.delete.assert_awaited_once()

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert "receiver_user_id" not in kwargs

    mock_schedule.assert_awaited_once_with(CHAT_ID, 888, chat.autodelete_settings, "captcha_success")


async def test_success_side_effects_skipped_when_claim_lost(db_session, monkeypatch):
    """Проигранный claim -> нет unrestrict/has_passed_captcha/delete/welcome, только callback.answer()."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    user = await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, ephemeral_message_id=111)

    mock_bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.captcha.claim_session", AsyncMock(return_value=False))

    callback = _make_callback()
    await _handle_success(callback, db_session, _make_i18n())

    mock_bot.restrict_chat_member.assert_not_awaited()
    mock_bot.delete_ephemeral_message.assert_not_awaited()
    mock_bot.send_message.assert_not_awaited()
    callback.message.delete.assert_not_awaited()
    callback.answer.assert_awaited_once_with()

    await db_session.refresh(user)
    assert user.has_passed_captcha is False

    session_obj = await _fetch_session(db_session)
    assert session_obj.status == CaptchaSessionStatus.PENDING


# ── captcha.py: _handle_retry ──────────────────────────────────────────────────


async def test_retry_edits_ephemeral(db_session, monkeypatch):
    """Ephemeral-сессия: retry зовёт edit_ephemeral_message_text, НЕ callback.message.edit_text."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, ephemeral_message_id=4242)
    await CaptchaService.create_session(CHAT_ID, USER_ID)

    mock_bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)

    callback = _make_callback()
    await _handle_retry(callback, db_session, _make_i18n())

    mock_bot.edit_ephemeral_message_text.assert_awaited_once()
    _, kwargs = mock_bot.edit_ephemeral_message_text.call_args
    assert kwargs["chat_id"] == CHAT_ID
    assert kwargs["receiver_user_id"] == USER_ID
    assert kwargs["ephemeral_message_id"] == 4242
    assert kwargs["reply_markup"] is not None
    callback.message.edit_text.assert_not_awaited()


async def test_retry_edits_legacy(db_session, monkeypatch):
    """Legacy-сессия (message_id): retry идёт старым путём — callback.message.edit_text."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, message_id=55)
    await CaptchaService.create_session(CHAT_ID, USER_ID)

    mock_bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)

    callback = _make_callback()
    await _handle_retry(callback, db_session, _make_i18n())

    callback.message.edit_text.assert_awaited_once()
    mock_bot.edit_ephemeral_message_text.assert_not_awaited()


# ── captcha.py: _handle_fail ───────────────────────────────────────────────────


async def test_fail_bans_and_deletes_ephemeral_when_claim_won(db_session, monkeypatch):
    """Выигранный claim(DECLINED): бан + удаление эфемерной капчи."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, ephemeral_message_id=111)

    mock_bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)

    callback = _make_callback()
    await _handle_fail(callback, db_session, _make_i18n())

    mock_bot.ban_chat_member.assert_awaited_once()
    mock_bot.delete_ephemeral_message.assert_awaited_once_with(
        chat_id=CHAT_ID, receiver_user_id=USER_ID, ephemeral_message_id=111
    )
    callback.message.delete.assert_not_awaited()

    session_obj = await _fetch_session(db_session)
    assert session_obj.status == CaptchaSessionStatus.DECLINED


async def test_fail_legacy_bans_and_deletes_via_callback(db_session, monkeypatch):
    """Legacy-сессия: бан + удаление через callback.message.delete()."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, message_id=77)

    mock_bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)

    callback = _make_callback()
    await _handle_fail(callback, db_session, _make_i18n())

    mock_bot.ban_chat_member.assert_awaited_once()
    mock_bot.delete_ephemeral_message.assert_not_awaited()
    callback.message.delete.assert_awaited_once()


async def test_fail_ban_only_after_claim(db_session, monkeypatch):
    """Проигранный claim -> бан НЕ вызывается, только callback.answer() без аргументов."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session, ephemeral_message_id=111)

    mock_bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.captcha.claim_session", AsyncMock(return_value=False))

    callback = _make_callback()
    await _handle_fail(callback, db_session, _make_i18n())

    mock_bot.ban_chat_member.assert_not_awaited()
    mock_bot.delete_ephemeral_message.assert_not_awaited()
    callback.message.delete.assert_not_awaited()
    callback.answer.assert_awaited_once_with()

    session_obj = await _fetch_session(db_session)
    assert session_obj.status == CaptchaSessionStatus.PENDING


# ── worker/captcha.py: kick_unverified_user (таймаут) ─────────────────────────


async def test_kick_ephemeral_edits_ephemeral_message_no_autodelete(db_session, monkeypatch):
    """Ephemeral timeout: edit_ephemeral_message_text, БЕЗ autodelete и БЕЗ edit_message_text(None)."""
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    session_obj = await _seed_session(
        db_session,
        ephemeral_message_id=555,
        expires_at=datetime.now().astimezone() - timedelta(seconds=1),
    )

    mock_bot = _make_mock_bot()
    mock_schedule = AsyncMock()
    monkeypatch.setattr("app.worker.captcha.bot", mock_bot)
    monkeypatch.setattr("app.worker.captcha.schedule_autodelete", mock_schedule)

    await kick_unverified_user(CHAT_ID, USER_ID, session_obj.id)

    mock_bot.edit_ephemeral_message_text.assert_awaited_once()
    _, kwargs = mock_bot.edit_ephemeral_message_text.call_args
    assert kwargs["chat_id"] == CHAT_ID
    assert kwargs["receiver_user_id"] == USER_ID
    assert kwargs["ephemeral_message_id"] == 555
    mock_bot.edit_message_text.assert_not_awaited()
    mock_schedule.assert_not_awaited()

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.EXPIRED


async def test_kick_legacy_edits_message_and_schedules_autodelete(db_session, monkeypatch):
    """Legacy timeout (message_id): edit_message_text + autodelete, как раньше (латентный баг закрыт)."""
    chat = await create_chat(
        db_session,
        id=CHAT_ID,
        captcha_enabled=True,
        autodelete_settings={"captcha_timeout": {"enabled": True, "delay": 5}},
    )
    await create_user(db_session, id=USER_ID)
    session_obj = await _seed_session(
        db_session,
        message_id=42,
        expires_at=datetime.now().astimezone() - timedelta(seconds=1),
    )

    mock_bot = _make_mock_bot()
    mock_schedule = AsyncMock()
    monkeypatch.setattr("app.worker.captcha.bot", mock_bot)
    monkeypatch.setattr("app.worker.captcha.schedule_autodelete", mock_schedule)

    await kick_unverified_user(CHAT_ID, USER_ID, session_obj.id)

    mock_bot.edit_message_text.assert_awaited_once()
    _, kwargs = mock_bot.edit_message_text.call_args
    assert kwargs["chat_id"] == CHAT_ID
    assert kwargs["message_id"] == 42
    mock_bot.edit_ephemeral_message_text.assert_not_awaited()
    mock_schedule.assert_awaited_once_with(CHAT_ID, 42, chat.autodelete_settings, "captcha_timeout")
