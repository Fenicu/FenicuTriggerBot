"""Права на команды модерации: админ только с can_restrict_members, создатель, анонимный админ."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.bot.filters.moderation import HasUserRights


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.mod.error.no.rights.return_value = "Bot has no rights"
    return i18n


def _make_message(
    status: str = "member",
    *,
    can_restrict_members: bool = False,
    chat_id: int = -1001,
    sender_chat_id: int | None = None,
    from_user_id: int | None = 42,
) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id)
    msg.bot = MagicMock()
    msg.from_user = MagicMock(id=from_user_id) if from_user_id is not None else None
    msg.sender_chat = MagicMock(id=sender_chat_id) if sender_chat_id is not None else None

    member = MagicMock(status=status)
    member.can_restrict_members = can_restrict_members
    msg.chat.get_member = AsyncMock(return_value=member)
    return msg


@patch("app.bot.filters.moderation.ephemeral_answer", new_callable=AsyncMock)
async def test_plain_member_is_denied(mock_ephemeral: AsyncMock) -> None:
    msg = _make_message(status="member")

    assert await HasUserRights()(msg, _make_i18n()) is False

    mock_ephemeral.assert_awaited_once()
    assert mock_ephemeral.call_args.args[2] == "Bot has no rights"


@patch("app.bot.filters.moderation.ephemeral_answer", new_callable=AsyncMock)
async def test_admin_without_restrict_rights_is_denied(mock_ephemeral: AsyncMock) -> None:
    msg = _make_message(status="administrator", can_restrict_members=False)

    assert await HasUserRights()(msg, _make_i18n()) is False

    mock_ephemeral.assert_awaited_once()


@patch("app.bot.filters.moderation.ephemeral_answer", new_callable=AsyncMock)
async def test_admin_with_restrict_rights_is_allowed(mock_ephemeral: AsyncMock) -> None:
    msg = _make_message(status="administrator", can_restrict_members=True)

    assert await HasUserRights()(msg, _make_i18n()) is True

    mock_ephemeral.assert_not_awaited()


@patch("app.bot.filters.moderation.ephemeral_answer", new_callable=AsyncMock)
async def test_creator_is_allowed_without_restrict_flag(mock_ephemeral: AsyncMock) -> None:
    msg = _make_message(status="creator", can_restrict_members=False)

    assert await HasUserRights()(msg, _make_i18n()) is True

    mock_ephemeral.assert_not_awaited()


@patch("app.bot.filters.moderation.ephemeral_answer", new_callable=AsyncMock)
async def test_anonymous_admin_is_allowed(mock_ephemeral: AsyncMock) -> None:
    msg = _make_message(status="member", chat_id=-1001, sender_chat_id=-1001)

    assert await HasUserRights()(msg, _make_i18n()) is True

    msg.chat.get_member.assert_not_awaited()
    mock_ephemeral.assert_not_awaited()


@patch("app.bot.filters.moderation.ephemeral_answer", new_callable=AsyncMock)
async def test_message_without_author_is_denied(mock_ephemeral: AsyncMock) -> None:
    msg = _make_message(from_user_id=None)

    assert await HasUserRights()(msg, _make_i18n()) is False

    mock_ephemeral.assert_not_awaited()
