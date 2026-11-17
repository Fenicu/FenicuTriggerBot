"""Автоудаление сервисных сообщений о входе и выходе участников."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Chat, Message, Update, User
from app.bot.middlewares.service_autodelete import ServiceAutodeleteMiddleware

CHAT_ID = -1001234567890
MESSAGE_ID = 555
BOT_ID = 987654321

pytestmark = pytest.mark.asyncio


def _user(user_id: int = 42, is_bot: bool = False) -> User:
    return User(id=user_id, is_bot=is_bot, first_name="Test")


def _chat(chat_id: int = CHAT_ID, chat_type: str = "supergroup") -> Chat:
    return Chat(id=chat_id, type=chat_type, title="Test Chat")


def _message(
    *,
    chat: Chat | None = None,
    message_id: int = MESSAGE_ID,
    from_user: User | None = None,
    new_chat_members: list[User] | None = None,
    left_chat_member: User | None = None,
    text: str | None = None,
) -> Message:
    return Message(
        message_id=message_id,
        date=0,
        chat=chat or _chat(),
        from_user=from_user or _user(),
        new_chat_members=new_chat_members,
        left_chat_member=left_chat_member,
        text=text,
    )


def _update(message: Message) -> Update:
    return Update(update_id=1, message=message)


def _db_chat(settings: dict | None) -> SimpleNamespace:
    return SimpleNamespace(autodelete_settings=settings)


@pytest.fixture(autouse=True)
def _delete_permission_cached():
    """По умолчанию право на удаление не закэшировано как отсутствующее."""
    with patch("app.core.permissions.is_missing", new_callable=AsyncMock, return_value=False):
        yield


@pytest.fixture
def middleware() -> ServiceAutodeleteMiddleware:
    return ServiceAutodeleteMiddleware()


def _assert_delete_published(mock_broker, *, delay: int, chat_id: int = CHAT_ID, message_id: int = MESSAGE_ID) -> None:
    mock_broker.publish.assert_awaited_once()
    kwargs = mock_broker.publish.call_args.kwargs
    assert kwargs["message"] == {"chat_id": chat_id, "message_id": message_id}
    assert kwargs["routing_key"] == "q.messages.delete"
    assert kwargs["headers"] == {"x-delay": delay * 1000}


async def _run(middleware, event: Update, data: dict) -> tuple[AsyncMock, object]:
    handler = AsyncMock(return_value="ok")
    result = await middleware(handler, event, data)
    return handler, result


async def test_join_schedules_delete_with_configured_delay(middleware, mock_broker):
    event = _update(_message(new_chat_members=[_user(user_id=7)]))
    data = {"db_chat": _db_chat({"service_join": {"enabled": True, "delay": 90}})}

    handler, result = await _run(middleware, event, data)

    _assert_delete_published(mock_broker, delay=90)
    handler.assert_awaited_once()
    assert result == "ok"


async def test_join_ignored_when_type_disabled(middleware, mock_broker):
    event = _update(_message(new_chat_members=[_user(user_id=7)]))
    data = {"db_chat": _db_chat({"service_join": {"enabled": False, "delay": 90}})}

    handler, _ = await _run(middleware, event, data)

    mock_broker.publish.assert_not_awaited()
    handler.assert_awaited_once()


async def test_join_ignored_when_type_absent(middleware, mock_broker):
    event = _update(_message(new_chat_members=[_user(user_id=7)]))
    data = {"db_chat": _db_chat({"welcome": {"enabled": True, "delay": 30}})}

    handler, _ = await _run(middleware, event, data)

    mock_broker.publish.assert_not_awaited()
    handler.assert_awaited_once()


async def test_join_ignored_without_settings(middleware, mock_broker):
    event = _update(_message(new_chat_members=[_user(user_id=7)]))
    data = {"db_chat": _db_chat(None)}

    handler, _ = await _run(middleware, event, data)

    mock_broker.publish.assert_not_awaited()
    handler.assert_awaited_once()


async def test_join_of_bot_still_scheduled(middleware, mock_broker):
    event = _update(_message(from_user=_user(user_id=7), new_chat_members=[_user(user_id=7, is_bot=True)]))
    data = {"db_chat": _db_chat({"service_join": {"enabled": True, "delay": 15}})}

    await _run(middleware, event, data)

    _assert_delete_published(mock_broker, delay=15)


async def test_leave_by_member_scheduled(middleware, mock_broker):
    event = _update(_message(from_user=_user(user_id=7), left_chat_member=_user(user_id=7)))
    data = {"db_chat": _db_chat({"service_leave": {"enabled": True, "delay": 45}})}

    handler, result = await _run(middleware, event, data)

    _assert_delete_published(mock_broker, delay=45)
    handler.assert_awaited_once()
    assert result == "ok"


async def test_leave_by_our_bot_still_scheduled(middleware, mock_broker):
    event = _update(_message(from_user=_user(user_id=BOT_ID, is_bot=True), left_chat_member=_user(user_id=7)))
    data = {"db_chat": _db_chat({"service_leave": {"enabled": True, "delay": 60}})}

    await _run(middleware, event, data)

    _assert_delete_published(mock_broker, delay=60)


async def test_private_chat_ignored(middleware, mock_broker):
    event = _update(_message(chat=_chat(chat_type="private"), new_chat_members=[_user(user_id=7)]))
    data = {"db_chat": _db_chat({"service_join": {"enabled": True, "delay": 30}})}

    await _run(middleware, event, data)

    mock_broker.publish.assert_not_awaited()


async def test_skipped_when_delete_permission_missing(middleware, mock_broker):
    event = _update(_message(new_chat_members=[_user(user_id=7)]))
    data = {"db_chat": _db_chat({"service_join": {"enabled": True, "delay": 30}})}

    with patch("app.core.permissions.is_missing", new_callable=AsyncMock, return_value=True) as is_missing:
        handler, _ = await _run(middleware, event, data)

    is_missing.assert_awaited_once_with(CHAT_ID, "can_delete_messages")
    mock_broker.publish.assert_not_awaited()
    handler.assert_awaited_once()


async def test_both_kinds_scheduled_once_as_join(middleware, mock_broker):
    event = _update(_message(new_chat_members=[_user(user_id=7)], left_chat_member=_user(user_id=8)))
    data = {
        "db_chat": _db_chat(
            {
                "service_join": {"enabled": True, "delay": 30},
                "service_leave": {"enabled": True, "delay": 60},
            }
        )
    }

    await _run(middleware, event, data)

    _assert_delete_published(mock_broker, delay=30)


async def test_plain_message_ignored(middleware, mock_broker):
    event = _update(_message(text="hello"))
    data = {"db_chat": _db_chat({"service_join": {"enabled": True, "delay": 30}})}

    handler, _ = await _run(middleware, event, data)

    mock_broker.publish.assert_not_awaited()
    handler.assert_awaited_once()


async def test_ignored_when_no_db_chat(middleware, mock_broker):
    event = _update(_message(new_chat_members=[_user(user_id=7)]))

    handler, _ = await _run(middleware, event, {})

    mock_broker.publish.assert_not_awaited()
    handler.assert_awaited_once()


async def test_schedule_failure_does_not_break_chain(middleware, caplog):
    event = _update(_message(new_chat_members=[_user(user_id=7)]))
    data = {"db_chat": _db_chat({"service_join": {"enabled": True, "delay": 30}})}

    with (
        patch(
            "app.bot.middlewares.service_autodelete.schedule_autodelete",
            new_callable=AsyncMock,
            side_effect=RuntimeError("broker is down"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        handler, result = await _run(middleware, event, data)

    handler.assert_awaited_once()
    assert result == "ok"
    assert any("autodelete" in record.message.lower() for record in caplog.records)
