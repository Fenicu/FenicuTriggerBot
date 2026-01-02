from datetime import datetime, timedelta

from aiogram import F, Router, html
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatPermissions, Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.bot.keyboards.moderation import (
    get_duration_keyboard,
    get_moderation_settings_keyboard,
)
from app.core.time_util import parse_time_string
from app.services.moderation_service import ModerationService

router = Router()


def parse_args(args: str | None) -> tuple[int | None, str | None]:
    """
    Парсит аргументы команды.
    Возвращает (duration_seconds, reason).
    Если время не указано, duration_seconds = None.
    """
    if not args:
        return None, None

    parts = args.split(maxsplit=1)
    possible_time = parts[0]

    seconds = parse_time_string(possible_time)

    if seconds is not None:
        reason = parts[1] if len(parts) > 1 else None
        return seconds, reason

    return None, args


async def check_admin_rights(message: Message, i18n: TranslatorRunner) -> bool:
    """Проверяет права администратора у пользователя."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.get("mod-error-no-rights"), parse_mode="HTML")
        return False
    return True


async def check_bot_rights(message: Message, i18n: TranslatorRunner) -> bool:
    """Проверяет права администратора у бота."""
    bot_member = await message.chat.get_member(message.bot.id)
    if bot_member.status != "administrator":
        await message.answer(i18n.get("mod-error-no-rights"), parse_mode="HTML")
        return False
    return True


async def get_target_user(message: Message) -> tuple[int | None, str | None]:
    """
    Получает целевого пользователя из reply.
    Возвращает (user_id, user_name).
    """
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return None, None

    user = message.reply_to_message.from_user
    return user.id, user.full_name


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject, i18n: TranslatorRunner) -> None:
    if not await check_admin_rights(message, i18n):
        return
    if not await check_bot_rights(message, i18n):
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        return

    target_member = await message.chat.get_member(user_id)
    if target_member.status in ("administrator", "creator"):
        await message.answer(i18n.get("mod-error-admin"), parse_mode="HTML")
        return

    duration, reason = parse_args(command.args)
    until_date = datetime.now() + timedelta(seconds=duration) if duration else None

    try:
        await message.chat.ban(user_id=user_id, until_date=until_date)

        msg_key = "mod-user-banned"
        await message.answer(i18n.get(msg_key, user=html.quote(user_name), reason=reason or "—"), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Error: {e}")


@router.message(Command("mute", "ro", "shhh"))
async def cmd_mute(message: Message, command: CommandObject, i18n: TranslatorRunner) -> None:
    if not await check_admin_rights(message, i18n):
        return
    if not await check_bot_rights(message, i18n):
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        return

    target_member = await message.chat.get_member(user_id)
    if target_member.status in ("administrator", "creator"):
        await message.answer(i18n.get("mod-error-admin"), parse_mode="HTML")
        return

    duration, reason = parse_args(command.args)

    until_date = datetime.now() + timedelta(seconds=duration) if duration else None

    permissions = ChatPermissions(can_send_messages=False)

    try:
        await message.chat.restrict(user_id=user_id, permissions=permissions, until_date=until_date)

        time_str = str(timedelta(seconds=duration)) if duration else "∞"
        await message.answer(
            i18n.get("mod-user-muted", user=html.quote(user_name), time=time_str, reason=reason or "—"),
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"Error: {e}")


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject, i18n: TranslatorRunner) -> None:
    if not await check_admin_rights(message, i18n):
        return
    if not await check_bot_rights(message, i18n):
        return

    user_id = None
    user_name = "User"

    if message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
        user_name = message.reply_to_message.from_user.full_name
    elif command.args:
        if command.args.isdigit():
            user_id = int(command.args)
            user_name = str(user_id)
        else:
            pass

    if not user_id:
        return

    try:
        await message.chat.unban(user_id=user_id, only_if_banned=True)
        await message.answer(i18n.get("mod-user-unbanned", user=html.quote(user_name)), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Error: {e}")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message, i18n: TranslatorRunner) -> None:
    if not await check_admin_rights(message, i18n):
        return
    if not await check_bot_rights(message, i18n):
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        return

    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
        can_change_info=True,
        can_pin_messages=True,
    )

    try:
        await message.chat.restrict(user_id=user_id, permissions=permissions)
        await message.answer(i18n.get("mod-user-unmuted", user=html.quote(user_name)), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Error: {e}")


@router.message(Command("kick"))
async def cmd_kick(message: Message, i18n: TranslatorRunner) -> None:
    if not await check_admin_rights(message, i18n):
        return
    if not await check_bot_rights(message, i18n):
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        return

    target_member = await message.chat.get_member(user_id)
    if target_member.status in ("administrator", "creator"):
        await message.answer(i18n.get("mod-error-admin"), parse_mode="HTML")
        return

    try:
        await message.chat.unban(user_id=user_id)
        await message.chat.ban(user_id=user_id, until_date=timedelta(seconds=31))
        await message.chat.unban(user_id=user_id)

        await message.answer(i18n.get("mod-user-kicked", user=html.quote(user_name)), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Error: {e}")


@router.message(Command("warn"))
async def cmd_warn(message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner) -> None:
    if not await check_admin_rights(message, i18n):
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        return

    target_member = await message.chat.get_member(user_id)
    if target_member.status in ("administrator", "creator"):
        await message.answer(i18n.get("mod-error-admin"), parse_mode="HTML")
        return

    reason = command.args
    service = ModerationService(session)

    await service.add_warn(message.chat.id, user_id, message.from_user.id, reason)

    count = await service.get_warn_count(message.chat.id, user_id)
    settings = await service.get_chat_settings(message.chat.id)

    await message.answer(
        i18n.get(
            "mod-warn-added", user=html.quote(user_name), cur=count, max=settings.warn_limit, reason=reason or "—"
        ),
        parse_mode="HTML",
    )

    if count >= settings.warn_limit:
        punishment = settings.warn_punishment
        duration = settings.warn_duration
        until_date = datetime.now() + timedelta(seconds=duration) if duration > 0 else None

        try:
            if punishment == "ban":
                await message.chat.ban(user_id=user_id, until_date=until_date)
            elif punishment == "mute":
                permissions = ChatPermissions(can_send_messages=False)
                await message.chat.restrict(user_id=user_id, permissions=permissions, until_date=until_date)

            await service.reset_warns(message.chat.id, user_id)

            punishment_text = "Бан" if punishment == "ban" else "Мут"
            await message.answer(
                i18n.get("mod-warn-reset", user=html.quote(user_name), punishment=punishment_text), parse_mode="HTML"
            )
        except Exception as e:
            await message.answer(f"Error applying punishment: {e}")


@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message, session: AsyncSession, i18n: TranslatorRunner) -> None:
    if not await check_admin_rights(message, i18n):
        return

    user_id, _user_name = await get_target_user(message)
    if not user_id:
        return

    service = ModerationService(session)
    removed = await service.remove_last_warn(message.chat.id, user_id)

    if removed:
        count = await service.get_warn_count(message.chat.id, user_id)
        settings = await service.get_chat_settings(message.chat.id)
        await message.answer(i18n.get("mod-warn-removed", cur=count, max=settings.warn_limit), parse_mode="HTML")
    else:
        await message.answer("У пользователя нет предупреждений.")


@router.message(Command("warns"))
async def cmd_warns(message: Message, session: AsyncSession, i18n: TranslatorRunner) -> None:
    user_id, user_name = await get_target_user(message)
    if not user_id:
        user_id = message.from_user.id
        user_name = message.from_user.full_name

    service = ModerationService(session)
    warns = await service.get_user_warns(message.chat.id, user_id)
    settings = await service.get_chat_settings(message.chat.id)

    if not warns:
        await message.answer(f"У пользователя {html.quote(user_name)} нет предупреждений.", parse_mode="HTML")
        return

    list_text = "\n".join([f"{w.created_at.strftime('%Y-%m-%d %H:%M')}: {w.reason or '—'}" for w in warns])

    await message.answer(
        i18n.get("mod-warns-list", user=html.quote(user_name), cur=len(warns), max=settings.warn_limit, list=list_text),
        parse_mode="HTML",
    )


@router.callback_query(ModerationSettingsCallback.filter(F.action == "menu"))
async def on_moderation_menu(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.get("error-no-rights"), show_alert=True)
        return

    service = ModerationService(session)
    chat = await service.get_chat_settings(callback.message.chat.id)

    keyboard = get_moderation_settings_keyboard(chat)
    await callback.message.edit_text(i18n.get("mod-settings-title"), reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(ModerationSettingsCallback.filter(F.action == "limit"))
async def on_limit_change(
    callback: CallbackQuery, callback_data: ModerationSettingsCallback, session: AsyncSession, i18n: TranslatorRunner
) -> None:
    service = ModerationService(session)
    chat = await service.get_chat_settings(callback.message.chat.id)

    new_limit = chat.warn_limit
    if callback_data.value == "incr":
        new_limit += 1
    elif callback_data.value == "decr":
        new_limit = max(2, new_limit - 1)

    if new_limit != chat.warn_limit:
        chat = await service.update_chat_settings(chat.id, warn_limit=new_limit)
        keyboard = get_moderation_settings_keyboard(chat)
        await callback.message.edit_reply_markup(reply_markup=keyboard)

    await callback.answer()


@router.callback_query(ModerationSettingsCallback.filter(F.action == "punishment"))
async def on_punishment_toggle(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    service = ModerationService(session)
    chat = await service.get_chat_settings(callback.message.chat.id)

    new_punishment = "mute" if chat.warn_punishment == "ban" else "ban"
    chat = await service.update_chat_settings(chat.id, warn_punishment=new_punishment)

    keyboard = get_moderation_settings_keyboard(chat)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@router.callback_query(ModerationSettingsCallback.filter(F.action == "duration"))
async def on_duration_action(
    callback: CallbackQuery, callback_data: ModerationSettingsCallback, session: AsyncSession, i18n: TranslatorRunner
) -> None:
    if callback_data.value == "menu":
        keyboard = get_duration_keyboard()
        await callback.message.edit_text("Выберите длительность наказания:", reply_markup=keyboard)
        await callback.answer()
    else:
        try:
            seconds = int(callback_data.value)
            service = ModerationService(session)
            chat = await service.update_chat_settings(callback.message.chat.id, warn_duration=seconds)

            keyboard = get_moderation_settings_keyboard(chat)
            await callback.message.edit_text(i18n.get("mod-settings-title"), reply_markup=keyboard, parse_mode="HTML")
            await callback.answer()
        except ValueError:
            await callback.answer("Invalid duration")
