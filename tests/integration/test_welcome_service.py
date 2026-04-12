"""Integration tests for welcome_service.

The welcome_service.send_welcome_message function is heavily coupled to Telegram Bot API
(aiogram Bot, Message, Chat, User objects). Since this is an integration test focused on
database interaction, we test the database-related aspects that support the welcome flow:
the welcome_enabled flag, welcome_message JSON storage, and template rendering with
chat variables from DB.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models.chat import Chat
from app.services.welcome_service import send_welcome_message
from tests.factories import create_chat


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, welcome_enabled=True)


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=43))
    bot.send_video = AsyncMock(return_value=MagicMock(message_id=44))
    bot.send_animation = AsyncMock(return_value=MagicMock(message_id=45))
    return bot


@pytest.fixture
def mock_aiogram_user():
    user = MagicMock()
    user.id = 123456
    user.username = "testuser"
    user.full_name = "Test User"
    user.first_name = "Test"
    return user


@pytest.fixture
def mock_aiogram_chat(chat):
    c = MagicMock()
    c.id = chat.id
    c.title = chat.title
    return c


# ── welcome_enabled / welcome_message DB storage ────────────────────────────


async def test_chat_welcome_disabled_by_default(db_session):
    chat = await create_chat(db_session)
    assert chat.welcome_enabled is False


async def test_chat_welcome_enabled_flag(db_session):
    chat = await create_chat(db_session, welcome_enabled=True)
    assert chat.welcome_enabled is True


async def test_chat_welcome_message_default_none(db_session):
    chat = await create_chat(db_session)
    assert chat.welcome_message is None


async def test_chat_welcome_message_json_storage(db_session):
    msg = {"text": "Hello, {{ user.full_name }}!"}
    chat = await create_chat(db_session, welcome_message=msg)
    assert chat.welcome_message == msg


async def test_chat_welcome_message_with_buttons(db_session):
    msg = {
        "text": "Welcome!",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "Rules", "url": "https://example.com/rules"}]
            ]
        },
    }
    chat = await create_chat(db_session, welcome_message=msg)
    assert chat.welcome_message["reply_markup"]["inline_keyboard"][0][0]["text"] == "Rules"


async def test_chat_welcome_message_photo(db_session):
    msg = {
        "photo": [{"file_id": "abc123", "width": 100, "height": 100}],
        "caption": "Welcome photo!",
    }
    chat = await create_chat(db_session, welcome_message=msg)
    assert chat.welcome_message["photo"][0]["file_id"] == "abc123"


# ── send_welcome_message integration ────────────────────────────────────────


@patch("app.services.welcome_service.schedule_autodelete", new_callable=AsyncMock)
async def test_send_welcome_returns_none_when_disabled(
    mock_autodelete, db_session, mock_bot, mock_aiogram_chat, mock_aiogram_user
):
    db_chat = await create_chat(db_session, welcome_enabled=False, welcome_message={"text": "Hi"})

    result = await send_welcome_message(
        mock_bot, db_session, mock_aiogram_chat, mock_aiogram_user, db_chat
    )
    assert result is None
    mock_bot.send_message.assert_not_called()


@patch("app.services.welcome_service.schedule_autodelete", new_callable=AsyncMock)
async def test_send_welcome_returns_none_when_no_message(
    mock_autodelete, db_session, mock_bot, mock_aiogram_chat, mock_aiogram_user
):
    db_chat = await create_chat(db_session, welcome_enabled=True, welcome_message=None)

    result = await send_welcome_message(
        mock_bot, db_session, mock_aiogram_chat, mock_aiogram_user, db_chat
    )
    assert result is None


@patch("app.services.welcome_service.schedule_autodelete", new_callable=AsyncMock)
async def test_send_welcome_text_message(
    mock_autodelete, db_session, mock_bot, mock_aiogram_chat, mock_aiogram_user
):
    db_chat = await create_chat(
        db_session,
        welcome_enabled=True,
        welcome_message={"text": "Hello, {{ user.full_name }}!"},
    )

    mock_aiogram_chat.id = db_chat.id
    result = await send_welcome_message(
        mock_bot, db_session, mock_aiogram_chat, mock_aiogram_user, db_chat
    )

    assert result is not None
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args
    assert "Hello, Test User!" in call_kwargs.kwargs.get("text", call_kwargs[1].get("text", ""))


@patch("app.services.welcome_service.schedule_autodelete", new_callable=AsyncMock)
async def test_send_welcome_calls_autodelete(
    mock_autodelete, db_session, mock_bot, mock_aiogram_chat, mock_aiogram_user
):
    db_chat = await create_chat(
        db_session,
        welcome_enabled=True,
        welcome_message={"text": "Hi!"},
        autodelete_settings={"welcome": 60},
    )

    mock_aiogram_chat.id = db_chat.id
    await send_welcome_message(
        mock_bot, db_session, mock_aiogram_chat, mock_aiogram_user, db_chat
    )

    mock_autodelete.assert_called_once()
