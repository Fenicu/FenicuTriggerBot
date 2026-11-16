"""check_triggers: контент триггера подгружается из БД по id после совпадения."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat as TgChat
from aiogram.types import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import trigger_service
from tests.factories import create_chat, create_trigger


@pytest.fixture(autouse=True)
def _real_trigger_cache(valkey_client):
    with patch("app.services.trigger_service.valkey", valkey_client):
        yield


def _make_message(chat_id: int, text: str) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.sender_chat = None
    msg.from_user = MagicMock(id=456, username="testuser", full_name="Test User")
    msg.text = text
    return msg


@patch("app.bot.handlers.matching._send_trigger_message", new_callable=AsyncMock)
async def test_matched_trigger_is_sent_with_content_from_database(mock_send, db_session: AsyncSession):
    from app.bot.handlers.matching import check_triggers

    chat = await create_chat(db_session, module_triggers=True)
    trigger = await create_trigger(db_session, chat.id, key_phrase="hello", content={"text": "Hi there"})
    await db_session.commit()

    # Первый вызов наполняет кэш, второй работает уже по кэшу без content
    await check_triggers(_make_message(chat.id, "hello"), db_session, chat)
    await check_triggers(_make_message(chat.id, "HELLO"), db_session, chat)

    assert mock_send.await_count == 2
    for call in mock_send.await_args_list:
        assert call.args[0] == {"text": "Hi there"}
        assert call.args[3].id == trigger.id


@patch("app.bot.handlers.matching._send_trigger_message", new_callable=AsyncMock)
async def test_sent_content_is_a_copy(mock_send, db_session: AsyncSession):
    """Подготовка контента (шаблоны) не должна менять объект, загруженный из БД."""
    from app.bot.handlers.matching import check_triggers

    chat = await create_chat(db_session, module_triggers=True)
    trigger = await create_trigger(
        db_session, chat.id, key_phrase="tpl", content={"text": "Hi {{ user.first_name }}"}, is_template=True
    )
    await db_session.commit()

    # Контекст шаблона уходит в процесс-пул -- нужны настоящие (сериализуемые) объекты
    msg = _make_message(chat.id, "tpl")
    msg.from_user = User(id=456, is_bot=False, first_name="Ann")
    msg.chat = TgChat(id=chat.id, type="supergroup", title="T")

    await check_triggers(msg, db_session, chat)

    assert mock_send.await_args.args[0]["text"] == "Hi Ann"
    await db_session.refresh(trigger)
    assert trigger.content == {"text": "Hi {{ user.first_name }}"}


@patch("app.bot.handlers.matching._send_trigger_message", new_callable=AsyncMock)
async def test_trigger_deleted_behind_stale_cache_does_not_reply(mock_send, db_session: AsyncSession):
    from app.bot.handlers.matching import check_triggers

    chat = await create_chat(db_session, module_triggers=True)
    trigger = await create_trigger(db_session, chat.id, key_phrase="hello")
    await db_session.commit()
    await trigger_service.get_triggers_by_chat(db_session, chat.id)

    # Удаление в обход инвалидации кэша: список в Valkey всё ещё содержит триггер
    trigger.is_deleted = True
    await db_session.commit()

    await check_triggers(_make_message(chat.id, "hello"), db_session, chat)

    mock_send.assert_not_awaited()
