"""Tests for app/api/deps.py — auth dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_authenticated_user,
    get_current_admin,
    require_chat_admin,
    validate_init_data,
    validate_init_data_from_query,
)
from app.api.v1.endpoints.auth import create_auth_token
from tests.factories import create_user


# ---------------------------------------------------------------------------
# validate_init_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_init_data_missing_header():
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data(authorization=None)
    assert exc_info.value.status_code == 401
    assert "missing" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_init_data_invalid_format():
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data(authorization="no-space-here")
    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_init_data_unknown_type():
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data(authorization="Basic dXNlcjpwYXNz")
    assert exc_info.value.status_code == 401
    assert "unknown" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_init_data_bearer_valid():
    token = create_auth_token(12345)
    result = await validate_init_data(authorization=f"Bearer {token}")
    assert result["type"] == "token"
    assert result["user_id"] == 12345


@pytest.mark.asyncio
async def test_validate_init_data_bearer_invalid():
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data(authorization="Bearer invalid.token")
    assert exc_info.value.status_code == 401
    assert "invalid or expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_init_data_bearer_expired():
    token = create_auth_token(12345, ttl_seconds=-1)
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# validate_init_data_from_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_from_query_missing_params():
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data_from_query(auth=None, auth_type=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_validate_from_query_token_valid():
    token = create_auth_token(99999)
    result = await validate_init_data_from_query(auth=token, auth_type="token")
    assert result["type"] == "token"
    assert result["user_id"] == 99999


@pytest.mark.asyncio
async def test_validate_from_query_token_invalid():
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data_from_query(auth="bad.token", auth_type="token")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_validate_from_query_unknown_type():
    with pytest.raises(HTTPException) as exc_info:
        await validate_init_data_from_query(auth="data", auth_type="magic")
    assert exc_info.value.status_code == 401
    assert "unknown" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# get_current_admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_admin_success(db_session: AsyncSession):
    user = await create_user(db_session, is_bot_moderator=True)
    await db_session.commit()

    token = create_auth_token(user.id)
    auth_info = {"type": "token", "user_id": user.id}

    from app.api.deps import _get_admin_from_auth_info

    admin = await _get_admin_from_auth_info(auth_info, db_session)
    assert admin.id == user.id


@pytest.mark.asyncio
async def test_get_current_admin_non_moderator_forbidden(db_session: AsyncSession):
    user = await create_user(db_session, is_bot_moderator=False)
    await db_session.commit()

    auth_info = {"type": "token", "user_id": user.id}

    from app.api.deps import _get_admin_from_auth_info

    with pytest.raises(HTTPException) as exc_info:
        await _get_admin_from_auth_info(auth_info, db_session)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# require_chat_admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_chat_admin_bot_moderator(db_session: AsyncSession):
    user = await create_user(db_session, is_bot_moderator=True)
    await db_session.commit()
    # Should not raise
    await require_chat_admin(user, -1001234567890)


@pytest.mark.asyncio
async def test_require_chat_admin_telegram_admin(db_session: AsyncSession):
    user = await create_user(db_session, is_bot_moderator=False)
    await db_session.commit()

    mock_member = MagicMock()
    mock_member.status = "administrator"

    with patch("app.api.deps.bot") as mock_bot:
        mock_bot.get_chat_member = AsyncMock(return_value=mock_member)
        await require_chat_admin(user, -1001234567890)


@pytest.mark.asyncio
async def test_require_chat_admin_regular_user_forbidden(db_session: AsyncSession):
    user = await create_user(db_session, is_bot_moderator=False)
    await db_session.commit()

    mock_member = MagicMock()
    mock_member.status = "member"

    with patch("app.api.deps.bot") as mock_bot:
        mock_bot.get_chat_member = AsyncMock(return_value=mock_member)
        with pytest.raises(HTTPException) as exc_info:
            await require_chat_admin(user, -1001234567890)
    assert exc_info.value.status_code == 403
