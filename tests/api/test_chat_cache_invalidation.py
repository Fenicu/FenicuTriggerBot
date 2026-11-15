from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.endpoints.auth import create_auth_token
from tests.factories import create_chat, create_user


@pytest.mark.parametrize("action", ["ban", "unban"])
async def test_ban_change_invalidates_cached_status(api_client, db_session, action):
    admin = await create_user(db_session, is_bot_moderator=True)
    chat = await create_chat(db_session)
    await db_session.commit()
    cache = AsyncMock()
    with patch("app.api.v1.endpoints.chats.valkey", cache, create=True):
        response = await api_client.post(
            f"/api/v1/chats/{chat.id}/{action}",
            json={"reason": "test"} if action == "ban" else None,
            headers={"Authorization": f"Bearer {create_auth_token(admin.id)}"},
        )
    assert response.status_code == 200
    cache.delete.assert_awaited_once_with(f"banned_chat:{chat.id}")


@pytest.mark.parametrize("language,invalidated", [("en", True), ("ru", False)])
async def test_language_change_invalidates_cache(api_client, db_session, language, invalidated):
    admin = await create_user(db_session, is_bot_moderator=True)
    chat = await create_chat(db_session, language_code="ru")
    await db_session.commit()
    cache = AsyncMock()
    with patch("app.api.v1.endpoints.chats.valkey", cache, create=True):
        response = await api_client.patch(
            f"/api/v1/chats/{chat.id}/full-settings",
            json={"language_code": language},
            headers={"Authorization": f"Bearer {create_auth_token(admin.id)}"},
        )
    assert response.status_code == 200
    if invalidated:
        cache.delete.assert_awaited_once_with(f"lang:{chat.id}")
    else:
        cache.delete.assert_not_awaited()
