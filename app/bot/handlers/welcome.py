import html
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.time_util import parse_time_string
from app.db.models.chat import Chat
from app.services.chat_service import update_chat_settings
from app.services.chat_variable_service import get_vars
from app.services.template_service import get_render_context, render_template

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("welcome"))
async def welcome_command(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """
    Управление приветствиями.
    /welcome set [timeout] (в реплае)
    /welcome delete / off
    /welcome test
    """
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    args = command.args.split() if command.args else []
    action = args[0] if args else None

    if not action:
        await message.answer(i18n.get("welcome-usage"), parse_mode="HTML")
        return

    if action == "set":
        if not message.reply_to_message:
            await message.answer(i18n.get("welcome-set-no-reply"), parse_mode="HTML")
            return

        timeout = 0
        if len(args) > 1:
            time_str = args[1]
            if time_str.isdigit():
                timeout = int(time_str)
            else:
                parsed = parse_time_string(time_str)
                if parsed is not None:
                    timeout = parsed
                else:
                    await message.answer(i18n.get("welcome-invalid-timeout"), parse_mode="HTML")
                    return

        reply = message.reply_to_message
        msg_data = reply.model_dump(mode="json", exclude_none=True)

        if hasattr(reply, "html_text") and reply.html_text:
            if "text" in msg_data:
                msg_data["text"] = reply.html_text
            elif "caption" in msg_data:
                msg_data["caption"] = reply.html_text

        await update_chat_settings(
            session, db_chat.id, welcome_enabled=True, welcome_message=msg_data, welcome_delete_timeout=timeout
        )

        await message.answer(i18n.get("welcome-set-success", timeout=timeout), parse_mode="HTML")

    elif action in ("delete", "off"):
        await update_chat_settings(
            session, db_chat.id, welcome_enabled=False, welcome_message=None, welcome_delete_timeout=0
        )
        await message.answer(i18n.get("welcome-disabled"), parse_mode="HTML")

    elif action == "test":
        if not db_chat.welcome_enabled or not db_chat.welcome_message:
            await message.answer(i18n.get("welcome-not-set"), parse_mode="HTML")
            return

        msg_data = db_chat.welcome_message.copy()

        variables = await get_vars(session, message.chat.id)
        context = get_render_context(message.from_user, message.chat, variables, db_chat.timezone)

        if msg_data.get("text"):
            try:
                msg_data["text"] = render_template(html.unescape(msg_data["text"]), context)
            except Exception as e:
                await message.answer(f"Template error: {e}")
                return

        if msg_data.get("caption"):
            try:
                msg_data["caption"] = render_template(html.unescape(msg_data["caption"]), context)
            except Exception as e:
                await message.answer(f"Template error: {e}")
                return

        msg_data.pop("entities", None)
        msg_data.pop("caption_entities", None)

        try:
            msg = Message.model_validate(msg_data)
            msg._bot = bot
            await msg.send_copy(
                chat_id=message.chat.id,
                parse_mode="HTML",
                reply_to_message_id=message.message_id,
            )

        except Exception as e:
            logger.error(f"Failed to send welcome test: {e}")
            await message.answer(i18n.get("error-unknown"), parse_mode="HTML")
