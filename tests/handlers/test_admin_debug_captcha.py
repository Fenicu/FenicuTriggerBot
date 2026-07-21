"""Тесты /debug_captcha (app/bot/handlers/admin.py) — сессия без message_id, кнопка с token в URL."""

from unittest.mock import AsyncMock, MagicMock

from aiogram.enums import ChatType
from sqlalchemy import select

from app.db.models.captcha_session import ChatCaptchaSession
from tests.factories import create_chat, create_user


def _make_message(user_id: int):
    msg = MagicMock()
    msg.chat = MagicMock(id=user_id, type=ChatType.PRIVATE)
    msg.from_user = MagicMock(id=user_id, username="admin", full_name="Admin")
    msg.answer = AsyncMock()
    return msg


def _make_i18n():
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    i18n.error.private.only.return_value = "Private only"
    return i18n


async def test_debug_captcha_command_creates_session_without_message_id_and_token_url(db_session):
    """Сессия создаётся с message_id=NULL, кнопка ведёт на webapp_captcha_url(token)."""
    from app.bot.handlers.admin import debug_captcha_command

    admin = await create_user(db_session, is_bot_moderator=True)
    # chat_id=from_user.id (личка с ботом) -- FK требует существующую запись чата.
    await create_chat(db_session, id=admin.id, type="private")
    await db_session.commit()

    msg = _make_message(admin.id)
    await debug_captcha_command(msg, db_session, _make_i18n(), admin)

    msg.answer.assert_awaited_once()
    call_args = msg.answer.call_args
    button = call_args.kwargs["reply_markup"].inline_keyboard[0][0]

    result = await db_session.execute(
        select(ChatCaptchaSession).where(ChatCaptchaSession.user_id == admin.id)
    )
    captcha_session = result.scalars().one()

    assert captcha_session.message_id is None
    assert captcha_session.token in button.web_app.url
    assert "/captcha?token=" in button.web_app.url


async def test_debug_captcha_command_rejects_non_moderator(db_session):
    """Не-модератор/не-админ -> отказ, сессия НЕ создаётся."""
    from app.bot.handlers.admin import debug_captcha_command

    user = await create_user(db_session, is_bot_moderator=False)
    await db_session.commit()

    msg = _make_message(user.id)
    await debug_captcha_command(msg, db_session, _make_i18n(), user)

    msg.answer.assert_awaited_once_with("No rights", parse_mode="HTML")

    result = await db_session.execute(
        select(ChatCaptchaSession).where(ChatCaptchaSession.user_id == user.id)
    )
    assert result.scalars().first() is None
