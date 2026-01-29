import asyncio
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_util import get_timezone
from app.db.models.chat import Chat
from app.db.models.chat_variable import ChatVariable
from app.db.models.trigger import AccessLevel, Trigger
from app.services.template_service import get_render_context, render_template
from app.services.trigger_service import (
    find_matches,
    get_triggers_by_chat,
    increment_usage,
)

logger = logging.getLogger(__name__)
router = Router()


async def _check_access(
    trigger: Trigger,
    message: Message,
) -> bool:
    """
    Проверяет, имеет ли пользователь доступ к выполнению триггера.

    Args:
        trigger: Триггер для проверки
        message: Сообщение от пользователя

    Returns:
        True если доступ разрешен, False иначе
    """
    if trigger.access_level == AccessLevel.ALL:
        return True

    member = await message.chat.get_member(message.from_user.id)

    if trigger.access_level == AccessLevel.ADMINS:
        return member.status in ("administrator", "creator")

    if trigger.access_level == AccessLevel.OWNER:
        return member.status == "creator"

    logger.warning(f"Unknown access level: {trigger.access_level}")
    return False


async def _get_chat_variables(
    session: AsyncSession,
    chat_id: int,
) -> dict[str, str]:
    """
    Получает переменные чата из базы данных.

    Args:
        session: Сессия базы данных
        chat_id: ID чата

    Returns:
        Словарь переменных чата
    """
    vars_stmt = select(ChatVariable).where(ChatVariable.chat_id == chat_id)
    vars_result = await session.execute(vars_stmt)
    return {var.key: var.value for var in vars_result.scalars()}


def _get_timezone(chat_timezone: str | None) -> ZoneInfo:
    """
    Получает часовой пояс для чата.

    Args:
        chat_timezone: Часовой пояс чата

    Returns:
        Объект ZoneInfo
    """
    if chat_timezone:
        try:
            return ZoneInfo(chat_timezone)
        except ZoneInfoNotFoundError:
            logger.debug(f"Invalid timezone '{chat_timezone}', using default")
    return get_timezone()


def _render_template_field(
    content: dict,
    field: str,
    context: dict,
    trigger_id: int,
) -> None:
    """
    Рендерит шаблонное поле контента.

    Args:
        content: Словарь контента
        field: Имя поля для рендеринга
        context: Контекст для шаблона
        trigger_id: ID триггера для логирования
    """
    if not content.get(field):
        return

    try:
        content[field] = render_template(content[field], context)
    except Exception as e:
        logger.warning(f"Error rendering template {field} for trigger {trigger_id}: {e}")


async def _prepare_content(
    content: dict,
    trigger: Trigger,
    message: Message,
    db_chat: Chat,
    session: AsyncSession,
) -> dict:
    """
    Подготавливает контент для отправки.

    Args:
        content: Исходный контент триггера
        trigger: Объект триггера
        message: Сообщение пользователя
        db_chat: Объект чата из БД
        session: Сессия базы данных

    Returns:
        Параметры для отправки сообщения
    """
    send_kwargs: dict = {}

    if not trigger.is_template:
        return send_kwargs

    send_kwargs["parse_mode"] = "HTML"
    content.pop("entities", None)
    content.pop("caption_entities", None)

    chat_vars = await _get_chat_variables(session, message.chat.id)
    tz = _get_timezone(db_chat.timezone)

    context = get_render_context(
        user=message.from_user,
        chat=message.chat,
        variables=chat_vars,
        timezone=tz,
    )

    _render_template_field(content, "text", context, trigger.id)
    _render_template_field(content, "caption", context, trigger.id)

    return send_kwargs


async def _send_trigger_message(
    content: dict,
    send_kwargs: dict,
    message: Message,
    trigger: Trigger,
    session: AsyncSession,
) -> None:
    """
    Отправляет сообщение триггера в чат.

    Args:
        content: Контент для отправки
        send_kwargs: Дополнительные параметры отправки
        message: Исходное сообщение пользователя
        trigger: Объект триггера
        session: Сессия базы данных
    """
    try:
        saved_msg = Message.model_validate(content)
        saved_msg._bot = message.bot

        if saved_msg.dice:
            await message.bot.send_dice(
                chat_id=message.chat.id,
                emoji=saved_msg.dice.emoji,
                **send_kwargs,
            )
        else:
            await saved_msg.send_copy(chat_id=message.chat.id, **send_kwargs)

        await increment_usage(session, trigger.id)
    except Exception:
        logger.exception("Error sending trigger message")


@router.message()
async def check_triggers(
    message: Message,
    session: AsyncSession,
    db_chat: Chat,
) -> None:
    """
    Проверяет сообщение на наличие совпадающих триггеров и отправляет ответы.
    """
    if not message.text:
        return

    if not db_chat.module_triggers:
        return

    triggers = await get_triggers_by_chat(session, message.chat.id)
    if not triggers:
        return

    matches = await find_matches(triggers, message.text)
    if not matches:
        return

    for i, match in enumerate(matches):
        if i > 0:
            await asyncio.sleep(0.5)

        if not await _check_access(match, message):
            continue

        try:
            content = match.content.copy()
            send_kwargs = await _prepare_content(content, match, message, db_chat, session)
            await _send_trigger_message(content, send_kwargs, message, match, session)
        except Exception:
            logger.exception("Error processing trigger")
