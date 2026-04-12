"""Tests for /api/v1/chats/{id}/welcome-media and /welcome-test endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from tests.factories import create_chat, create_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_headers(user_id: int) -> dict[str, str]:
    token = create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_admin(session: AsyncSession) -> int:
    user = await create_user(session, is_bot_moderator=True, first_name="Admin")
    await session.commit()
    return user.id


# ---------------------------------------------------------------------------
# POST /chats/{id}/welcome-test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_welcome_test_success(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(
        db_session,
        type="supergroup",
        welcome_enabled=True,
        welcome_message={"text": "Hello, {first_name}!"},
    )
    await db_session.commit()

    mock_tg_chat = MagicMock()
    mock_tg_chat.id = chat.id

    with (
        patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock),
        patch("app.api.v1.endpoints.welcome.bot") as mock_bot,
        patch("app.api.v1.endpoints.welcome.send_welcome_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_bot.get_chat = AsyncMock(return_value=mock_tg_chat)
        mock_send.return_value = MagicMock()  # truthy = success

        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-test",
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_welcome_test_no_message_set(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(
        db_session,
        type="supergroup",
        welcome_enabled=True,
        welcome_message=None,
    )
    await db_session.commit()

    with patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock):
        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-test",
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 400
    assert "not set" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_welcome_test_chat_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)

    with patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock):
        resp = await api_client.post(
            "/api/v1/chats/-999999999999/welcome-test",
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_welcome_test_send_fails(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(
        db_session,
        type="supergroup",
        welcome_enabled=True,
        welcome_message={"text": "Hello!"},
    )
    await db_session.commit()

    mock_tg_chat = MagicMock()
    mock_tg_chat.id = chat.id

    with (
        patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock),
        patch("app.api.v1.endpoints.welcome.bot") as mock_bot,
        patch("app.api.v1.endpoints.welcome.send_welcome_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_bot.get_chat = AsyncMock(return_value=mock_tg_chat)
        mock_send.return_value = None  # send failed

        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-test",
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 500
    assert "failed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_welcome_test_unauthenticated(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()
    resp = await api_client.post(f"/api/v1/chats/{chat.id}/welcome-test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_welcome_test_cannot_access_chat(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(
        db_session,
        type="supergroup",
        welcome_enabled=True,
        welcome_message={"text": "Hello!"},
    )
    await db_session.commit()

    with (
        patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock),
        patch("app.api.v1.endpoints.welcome.bot") as mock_bot,
    ):
        mock_bot.get_chat = AsyncMock(side_effect=Exception("Bot was kicked"))

        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-test",
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 400
    assert "cannot access" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /chats/{id}/welcome-media
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_welcome_media_unsupported_type(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    with patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock):
        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-media",
            files={"file": ("test.txt", b"Hello, world!", "text/plain")},
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 400
    assert "unsupported" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_welcome_media_file_too_large(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    # Create content larger than 10MB
    large_content = b"\xff\xd8\xff" + b"\x00" * (11 * 1024 * 1024)

    with patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock):
        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-media",
            files={"file": ("big.jpg", large_content, "image/jpeg")},
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_welcome_media_content_mismatch(api_client: AsyncClient, db_session: AsyncSession):
    """Claimed type doesn't match actual file magic bytes."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    # Claim image/jpeg but send PNG magic bytes
    content = b"\x89PNG" + b"\x00" * 100

    with patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock):
        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-media",
            files={"file": ("test.jpg", content, "image/jpeg")},
            headers=_user_headers(admin_id),
        )
    # validate_file_type returns "image/png" which is still in ALLOWED_CONTENT_TYPES,
    # so this should succeed as long as bot upload works
    # Actually: actual_type will be image/png, actual_type is in ALLOWED_CONTENT_TYPES, so no error from validation
    # But we need to mock the bot upload
    # Let's test the case where content doesn't match any known type
    random_content = b"\x01\x02\x03\x04" * 25
    with patch("app.api.v1.endpoints.welcome.require_chat_admin", new_callable=AsyncMock):
        resp = await api_client.post(
            f"/api/v1/chats/{chat.id}/welcome-media",
            files={"file": ("test.jpg", random_content, "image/jpeg")},
            headers=_user_headers(admin_id),
        )
    assert resp.status_code == 400
    assert "doesn't match" in resp.json()["detail"].lower()
