import html
import logging

from aiogram import Bot
from aiogram.types import Chat as AiogramChat
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broker import broker, delayed_exchange
from app.db.models.chat import Chat
from app.services.chat_variable_service import get_vars
from app.services.template_service import get_render_context, render_template

logger = logging.getLogger(__name__)


async def send_welcome_message(
    bot: Bot,
    session: AsyncSession,
    chat: AiogramChat,
    user: User,
    db_chat: Chat,
) -> Message | None:
    """
    Отправляет приветственное сообщение в чат.
    """
    if not db_chat.welcome_enabled or not db_chat.welcome_message:
        return None

    msg_data = db_chat.welcome_message.copy()
    variables = await get_vars(session, chat.id)
    context = get_render_context(user, chat, variables, db_chat.timezone)

    if msg_data.get("text"):
        try:
            msg_data["text"] = render_template(html.unescape(msg_data["text"]), context)
        except Exception as e:
            logger.error(f"Template error: {e}")

    if msg_data.get("caption"):
        try:
            msg_data["caption"] = render_template(html.unescape(msg_data["caption"]), context)
        except Exception as e:
            logger.error(f"Template error: {e}")

    # Удаляем сущности, так как они могут не соответствовать новому тексту
    msg_data.pop("entities", None)
    msg_data.pop("caption_entities", None)

    # Собираем reply_markup из данных сообщения
    reply_markup = None
    if msg_data.get("reply_markup") and msg_data["reply_markup"].get("inline_keyboard"):
        rows = []
        for row in msg_data["reply_markup"]["inline_keyboard"]:
            buttons = [
                InlineKeyboardButton(text=btn["text"], url=btn["url"])
                for btn in row
                if btn.get("text") and btn.get("url")
            ]
            if buttons:
                rows.append(buttons)
        if rows:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=rows)

    sent_msg = None
    try:
        if "message_id" in msg_data:
            # Если это копия сообщения (например, пересланное) — legacy формат
            msg = Message.model_validate(msg_data)
            msg._bot = bot
            sent_msg = await msg.send_copy(chat_id=chat.id, parse_mode="HTML")
        elif msg_data.get("photo"):
            # Фото с опциональной подписью
            photo_list = msg_data["photo"]
            file_id = photo_list[-1]["file_id"]
            sent_msg = await bot.send_photo(
                chat_id=chat.id,
                photo=file_id,
                caption=msg_data.get("caption"),
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        elif msg_data.get("video"):
            # Видео с опциональной подписью
            file_id = msg_data["video"]["file_id"]
            sent_msg = await bot.send_video(
                chat_id=chat.id,
                video=file_id,
                caption=msg_data.get("caption"),
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        elif msg_data.get("animation"):
            # Анимация (GIF) с опциональной подписью
            file_id = msg_data["animation"]["file_id"]
            sent_msg = await bot.send_animation(
                chat_id=chat.id,
                animation=file_id,
                caption=msg_data.get("caption"),
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        else:
            # Обычное текстовое сообщение
            sent_msg = await bot.send_message(
                chat_id=chat.id,
                text=msg_data.get("text", ""),
                reply_markup=reply_markup,
                parse_mode="HTML",
            )

        if db_chat.welcome_delete_timeout > 0 and sent_msg:
            await broker.publish(
                message={"chat_id": chat.id, "message_id": sent_msg.message_id},
                exchange=delayed_exchange,
                routing_key="q.messages.delete",
                headers={"x-delay": db_chat.welcome_delete_timeout * 1000},
            )

        return sent_msg

    except Exception as e:
        logger.error(f"Failed to send welcome message: {e}")
        return None
