"""Синхронизация настроек самого бота (Bot API 10.5, setMySettings)."""

import logging

from aiogram import Bot

logger = logging.getLogger(__name__)

# Без can_read_all_group_messages бот не видит сообщения групп, а без
# supports_join_request_queries Telegram не шлёт ему заявки на вступление.
_DESIRED_SETTINGS: dict[str, bool] = {
    "can_read_all_group_messages": True,
    "can_join_groups": True,
    "supports_join_request_queries": True,
}


async def sync_bot_settings(bot: Bot) -> None:
    """Включить недостающие настройки бота; ошибки не должны ломать старт."""
    try:
        me = await bot.get_me()
        changes = {
            name: (getattr(me, name), desired)
            for name, desired in _DESIRED_SETTINGS.items()
            if getattr(me, name) != desired
        }
        if not changes:
            logger.debug("Bot settings are up to date")
            return
        await bot.set_my_settings(**{name: new for name, (_, new) in changes.items()})
    except Exception as exc:
        logger.warning("Failed to sync bot settings: %s", exc)
        return

    for name, (old, new) in changes.items():
        logger.info("Bot setting %s changed: %s -> %s", name, old, new)
