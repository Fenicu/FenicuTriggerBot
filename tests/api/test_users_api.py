"""Tests for /api/v1/users/ endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from app.core.config import settings
from tests.factories import create_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_headers(user_id: int) -> dict[str, str]:
    token = create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_admin(session: AsyncSession, *, moderator: bool = True) -> int:
    user = await create_user(session, is_bot_moderator=moderator)
    await session.commit()
    return user.id


# ---------------------------------------------------------------------------
# GET /users/  (list)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_empty(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get("/api/v1/users/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    # At least the admin user exists
    assert body["pagination"]["total"] >= 1


@pytest.mark.asyncio
async def test_list_users_returns_items(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_user(db_session, first_name="Alice", username="alice")
    await create_user(db_session, first_name="Bob", username="bob")
    await db_session.commit()

    resp = await api_client.get("/api/v1/users/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    # admin + 2 users
    assert body["pagination"]["total"] == 3
    assert len(body["items"]) == 3


@pytest.mark.asyncio
async def test_list_users_search_by_name(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_user(db_session, first_name="Alice", username="alice")
    await create_user(db_session, first_name="Bob", username="bob")
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/users/", params={"query": "Alice"}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["first_name"] == "Alice"


@pytest.mark.asyncio
async def test_list_users_pagination(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    for i in range(5):
        await create_user(db_session, first_name=f"User{i}")
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/users/", params={"page": 1, "limit": 2}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 6  # admin + 5
    assert len(body["items"]) == 2
    assert body["pagination"]["total_pages"] == 3


@pytest.mark.asyncio
async def test_list_users_filter_trusted(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_user(db_session, first_name="Trusted", is_trusted=True)
    await create_user(db_session, first_name="NotTrusted", is_trusted=False)
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/users/", params={"is_trusted": True}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    # All returned users should be trusted
    for item in body["items"]:
        assert item["is_trusted"] is True


@pytest.mark.asyncio
async def test_list_users_filter_moderator(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_user(db_session, first_name="Regular", is_bot_moderator=False)
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/users/", params={"is_bot_moderator": True}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["is_bot_moderator"] is True


@pytest.mark.asyncio
async def test_list_users_unauthenticated(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/users/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_users_non_admin_forbidden(api_client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, is_bot_moderator=False)
    await db_session.commit()

    resp = await api_client.get("/api/v1/users/", headers=_admin_headers(user.id))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /users/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_by_id(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    user = await create_user(db_session, first_name="TestUser", username="testuser")
    await db_session.commit()

    with patch("app.api.v1.endpoints.users.bot") as mock_bot:
        mock_bot.get_chat = AsyncMock(side_effect=Exception("Not found"))
        resp = await api_client.get(
            f"/api/v1/users/{user.id}", headers=_admin_headers(admin_id)
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user.id
    assert body["first_name"] == "TestUser"
    assert body["username"] == "testuser"


@pytest.mark.asyncio
async def test_get_user_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get("/api/v1/users/999999999", headers=_admin_headers(admin_id))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User not found"


# ---------------------------------------------------------------------------
# POST /users/{id}/role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_role_trusted(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    user = await create_user(db_session, is_trusted=False, is_bot_moderator=False)
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/users/{user.id}/role",
        json={"is_trusted": True},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    assert resp.json()["is_trusted"] is True


@pytest.mark.asyncio
async def test_update_user_role_moderator_by_non_superadmin_forbidden(
    api_client: AsyncClient, db_session: AsyncSession
):
    """Only BOT_ADMINS can set is_bot_moderator — a regular moderator cannot."""
    admin_id = await _seed_admin(db_session)
    user = await create_user(db_session, is_bot_moderator=False)
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/users/{user.id}/role",
        json={"is_bot_moderator": True},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 403
    assert "super admins" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_user_role_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.post(
        "/api/v1/users/999999999/role",
        json={"is_trusted": True},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 404
