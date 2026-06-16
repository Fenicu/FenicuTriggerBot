"""Handler test fixtures — aiogram mocks."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _mock_externals():
    with (
        patch("app.core.valkey.valkey") as mock_v,
        patch("app.core.broker.broker") as mock_b,
        patch("app.core.storage.storage") as mock_s,
    ):
        mock_v.get = AsyncMock(return_value=None)
        mock_v.set = AsyncMock()
        mock_v.delete = AsyncMock()
        mock_v.exists = AsyncMock(return_value=0)
        mock_v.publish = AsyncMock()
        mock_b.publish = AsyncMock()
        mock_s.delete_file = AsyncMock()
        yield


def _make_from_user(user_id: int = 42, username: str = "testmod", full_name: str = "Test Mod"):
    """Create a mock from_user object."""
    from_user = MagicMock()
    from_user.id = user_id
    from_user.username = username
    from_user.full_name = full_name
    return from_user


def _make_callback(
    data: str,
    user_id: int = 42,
    username: str = "testmod",
    full_name: str = "Test Mod",
    html_text: str = "<b>Alert text</b>",
    chat_id: int = -1001234567890,
) -> MagicMock:
    """Create a mock CallbackQuery."""
    callback = MagicMock()
    callback.data = data
    callback.from_user = _make_from_user(user_id, username, full_name)
    callback.answer = AsyncMock()

    callback.message = MagicMock()
    callback.message.html_text = html_text
    callback.message.rich_message = None
    callback.message.edit_text = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = chat_id
    callback.message.text = ""
    callback.message.reply_markup = None

    return callback
