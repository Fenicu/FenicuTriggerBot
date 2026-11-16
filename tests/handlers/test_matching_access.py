"""Проверка доступа к триггерам: устойчивость к ошибкам Telegram и кэш статуса участника."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from app.db.models.trigger import AccessLevel
from app.services.trigger_service import TriggerContentSnapshot


@pytest.fixture(autouse=True)
def _real_member_status_cache(valkey_client):
    """Кэш статуса участника -- на настоящем Valkey (общий conftest подменяет его моком)."""
    import app.bot.member_status  # noqa: F401

    with patch("app.bot.member_status.valkey", valkey_client):
        yield


def _make_message(chat_id: int, user_id: int = 456, member_status: str = "member") -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.sender_chat = None
    msg.from_user = MagicMock(id=user_id, username="testuser", full_name="Test User")
    msg.text = "key"
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status=member_status))
    return msg


def _trigger(access_level: AccessLevel, trigger_id: int = 1) -> MagicMock:
    trigger = MagicMock()
    trigger.id = trigger_id
    trigger.access_level = access_level
    trigger.content = {"text": "answer"}
    return trigger


async def test_check_access_telegram_error_means_no_access(valkey_client):
    from app.bot.handlers.matching import _check_access

    msg = _make_message(-100901)
    msg.chat.get_member = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message="USER_ID_INVALID"))

    assert await _check_access(_trigger(AccessLevel.ADMINS), msg) is False


async def test_check_access_network_error_means_no_access(valkey_client):
    from app.bot.handlers.matching import _check_access

    msg = _make_message(-100902)
    msg.chat.get_member = AsyncMock(side_effect=TelegramNetworkError(method=MagicMock(), message="timeout"))

    assert await _check_access(_trigger(AccessLevel.OWNER), msg) is False


async def test_check_access_caches_member_status(valkey_client):
    from app.bot.handlers.matching import _check_access

    msg = _make_message(-100903, member_status="administrator")

    assert await _check_access(_trigger(AccessLevel.ADMINS), msg) is True
    assert await _check_access(_trigger(AccessLevel.ADMINS), msg) is True
    assert await _check_access(_trigger(AccessLevel.OWNER), msg) is False

    msg.chat.get_member.assert_awaited_once()
    ttl = await valkey_client.ttl("member_status:-100903:456")
    assert 0 < ttl <= 60


async def test_check_access_cache_is_per_user(valkey_client):
    from app.bot.handlers.matching import _check_access

    admin = _make_message(-100904, user_id=1, member_status="creator")
    member = _make_message(-100904, user_id=2, member_status="member")

    assert await _check_access(_trigger(AccessLevel.OWNER), admin) is True
    assert await _check_access(_trigger(AccessLevel.OWNER), member) is False


async def test_check_access_works_without_valkey():
    """Недоступный Valkey не ломает проверку: статус берётся из Telegram."""
    from app.bot.handlers.matching import _check_access

    broken = MagicMock()
    broken.get = AsyncMock(side_effect=ConnectionError("down"))
    broken.set = AsyncMock(side_effect=ConnectionError("down"))
    msg = _make_message(-100905, member_status="administrator")

    with patch("app.bot.member_status.valkey", broken):
        assert await _check_access(_trigger(AccessLevel.ADMINS), msg) is True


@patch("app.bot.handlers.matching._send_trigger_message", new_callable=AsyncMock)
@patch("app.bot.handlers.matching._prepare_content", new_callable=AsyncMock)
@patch("app.bot.handlers.matching.find_matches", new_callable=AsyncMock)
@patch("app.bot.handlers.matching.get_triggers_by_chat", new_callable=AsyncMock)
async def test_access_check_failure_does_not_drop_remaining_triggers(
    mock_get_triggers, mock_find, mock_prepare, mock_send
):
    """Сбой проверки доступа одного триггера не отменяет остальные совпавшие."""
    from app.bot.handlers import matching as matching_module
    from app.bot.handlers.matching import check_triggers

    admin_trigger = _trigger(AccessLevel.ADMINS, 1)
    open_trigger = _trigger(AccessLevel.ALL, 2)
    mock_get_triggers.return_value = [admin_trigger, open_trigger]
    mock_find.return_value = [admin_trigger, open_trigger]
    mock_prepare.return_value = {}

    msg = _make_message(-100906)
    db_chat = MagicMock(module_triggers=True)

    with (
        patch.object(matching_module, "_check_access", AsyncMock(side_effect=[RuntimeError("boom"), True])),
        patch.object(matching_module.asyncio, "sleep", new_callable=AsyncMock),
        patch.object(
            matching_module,
            "get_trigger_content_snapshot",
            AsyncMock(
                return_value=TriggerContentSnapshot(
                    content={"text": "answer"},
                    access_level=AccessLevel.ALL,
                    is_template=False,
                    rich=False,
                )
            ),
            create=True,
        ),
    ):
        await check_triggers(msg, MagicMock(), db_chat)

    mock_send.assert_awaited_once()
    assert mock_send.call_args.args[3].id == 2
