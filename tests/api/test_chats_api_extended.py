"""Extended tests for /api/v1/chats/ endpoints — settings, trust edge cases, ban/unban."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from app.core.config import settings
from tests.factories import create_banned_chat, create_chat, create_trigger, create_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_headers(user_id: int) -> dict[str, str]:
    token = create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _user_headers(user_id: int) -> dict[str, str]:
    token = create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_admin(session: AsyncSession, *, moderator: bool = True) -> int:
    user = await create_user(session, is_bot_moderator=moderator)
    await session.commit()
    return user.id


# ---------------------------------------------------------------------------
# PATCH /chats/{id}/settings — extended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_settings_timezone_only(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/settings",
        json={"timezone": "Asia/Tokyo"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "Asia/Tokyo"


@pytest.mark.asyncio
async def test_update_settings_module_moderation(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup", module_moderation=True)
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/settings",
        json={"module_moderation": False},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    assert resp.json()["module_moderation"] is False


@pytest.mark.asyncio
async def test_update_settings_all_fields(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/settings",
        json={
            "timezone": "America/New_York",
            "module_triggers": False,
            "module_moderation": False,
        },
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "America/New_York"
    assert body["module_triggers"] is False
    assert body["module_moderation"] is False


@pytest.mark.asyncio
async def test_update_settings_empty_body(api_client: AsyncClient, db_session: AsyncSession):
    """Sending empty JSON should succeed (no-op)."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup", timezone="UTC")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/settings",
        json={},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "UTC"


# ---------------------------------------------------------------------------
# POST /chats/{id}/trust — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_trust_preserves_ban_status(api_client: AsyncClient, db_session: AsyncSession):
    """Toggling trust on a banned chat should still show ban status."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, is_trusted=False, type="supergroup")
    await create_banned_chat(db_session, chat.id, reason="spam")
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/chats/{chat.id}/trust", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_trusted"] is True
    assert body["is_banned"] is True
    assert body["ban_reason"] == "spam"


@pytest.mark.asyncio
async def test_toggle_trust_unauthenticated(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()
    resp = await api_client.post(f"/api/v1/chats/{chat.id}/trust")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /chats/{id}/ban — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ban_already_banned_chat(api_client: AsyncClient, db_session: AsyncSession):
    """Banning an already-banned chat should not fail."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await create_banned_chat(db_session, chat.id, reason="first ban")
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/chats/{chat.id}/ban",
        json={"reason": "second ban"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    assert resp.json()["is_banned"] is True


# ---------------------------------------------------------------------------
# GET /chats/{id}/full-settings (webapp endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_full_settings(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(
        db_session,
        type="supergroup",
        captcha_enabled=True,
        captcha_type="emoji",
        captcha_timeout=120,
        welcome_enabled=True,
    )
    await db_session.commit()

    resp = await api_client.get(
        f"/api/v1/chats/{chat.id}/full-settings", headers=_user_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["captcha_enabled"] is True
    assert body["captcha_type"] == "emoji"
    assert body["captcha_timeout"] == 120
    assert body["welcome_enabled"] is True
    assert body["is_creator"] is True  # admin is bot_moderator


@pytest.mark.asyncio
async def test_get_full_settings_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get(
        "/api/v1/chats/-999999999999/full-settings", headers=_user_headers(admin_id)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_full_settings_unauthenticated(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()
    resp = await api_client.get(f"/api/v1/chats/{chat.id}/full-settings")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /chats/{id}/full-settings (webapp endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_full_settings_captcha(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/full-settings",
        json={"captcha_enabled": True, "captcha_type": "webapp", "captcha_timeout": 60},
        headers=_user_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["captcha_enabled"] is True
    assert body["captcha_type"] == "webapp"
    assert body["captcha_timeout"] == 60


@pytest.mark.asyncio
async def test_update_full_settings_moderation(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/full-settings",
        json={
            "module_moderation": True,
            "warn_limit": 5,
            "warn_punishment": "mute",
            "warn_duration": 3600,
        },
        headers=_user_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["warn_limit"] == 5
    assert body["warn_punishment"] == "mute"
    assert body["warn_duration"] == 3600


@pytest.mark.asyncio
async def test_update_full_settings_welcome(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    welcome_msg = {"text": "Welcome, {first_name}!"}
    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/full-settings",
        json={"welcome_enabled": True, "welcome_message": welcome_msg},
        headers=_user_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["welcome_enabled"] is True
    assert body["welcome_message"]["text"] == "Welcome, {first_name}!"


@pytest.mark.asyncio
async def test_update_full_settings_locked_section(api_client: AsyncClient, db_session: AsyncSession):
    """Non-creator users cannot modify fields in locked sections."""
    # Create a regular (non-moderator, non-BOT_ADMIN) user
    user = await create_user(db_session, is_bot_moderator=False)
    chat = await create_chat(
        db_session,
        type="supergroup",
        settings_locked_sections=["captcha"],
        captcha_enabled=False,
    )
    await db_session.commit()

    # Mock require_chat_admin to let user pass (simulating TG admin),
    # and mock bot.get_chat_member to return non-creator status
    with (
        patch("app.api.v1.endpoints.chats.require_chat_admin", new_callable=AsyncMock),
        patch("app.api.v1.endpoints.chats.bot") as mock_bot,
    ):
        mock_member = MagicMock()
        mock_member.status = "administrator"
        mock_bot.get_chat_member = AsyncMock(return_value=mock_member)

        resp = await api_client.patch(
            f"/api/v1/chats/{chat.id}/full-settings",
            json={"captcha_enabled": True},
            headers=_user_headers(user.id),
        )
    assert resp.status_code == 200
    # The field should be silently dropped because section is locked
    assert resp.json()["captcha_enabled"] is False


@pytest.mark.asyncio
async def test_update_full_settings_invalid_warn_punishment_422(
    api_client: AsyncClient, db_session: AsyncSession
):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/full-settings",
        json={"warn_punishment": "kick"},
        headers=_user_headers(admin_id),
    )
    assert resp.status_code == 422
