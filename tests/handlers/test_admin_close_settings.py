"""Закрытие меню настроек: удалять сообщение может только администратор."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.bot.handlers.admin import close_settings


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    return i18n


def _make_callback(status: str = "administrator") -> MagicMock:
    callback = MagicMock()
    callback.from_user = MagicMock(id=555)
    callback.message = MagicMock()
    callback.message.delete = AsyncMock()
    callback.message.chat = MagicMock(id=-1001)
    callback.message.chat.get_member = AsyncMock(return_value=MagicMock(status=status))
    callback.answer = AsyncMock()
    return callback


async def test_member_cannot_close_settings_message() -> None:
    callback = _make_callback(status="member")

    await close_settings(callback, _make_i18n())

    callback.message.delete.assert_not_awaited()
    callback.answer.assert_awaited_once_with("No rights", show_alert=True)


@pytest.mark.parametrize("status", ["administrator", "creator"])
async def test_admin_closes_settings_message(status: str) -> None:
    callback = _make_callback(status=status)

    await close_settings(callback, _make_i18n())

    callback.message.delete.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
