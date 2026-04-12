"""Tests for /api/v1/triggers/{id}/preview endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trigger import ModerationStatus
from app.services.preview_service import generate_preview_token
from tests.factories import create_chat, create_trigger, create_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_preview_url(trigger_id: int) -> str:
    token = generate_preview_token(trigger_id)
    return f"/api/v1/triggers/{trigger_id}/preview?token={token}"


# The preview endpoint creates its own session from the module-level engine,
# bypassing the test db_session override.  We patch async_session so it
# returns the test session instead.


def _patch_preview_session(db_session: AsyncSession):
    """Return a context manager that patches the preview module's session factory."""

    class _FakeCtx:
        """Mimic `async with async_session() as session:`."""

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            pass

    fake_factory = MagicMock(return_value=_FakeCtx())
    return patch("app.api.v1.endpoints.preview.async_session", fake_factory)


# ---------------------------------------------------------------------------
# GET /triggers/{id}/preview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_valid_token(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, content={"text": "Hello preview!"})
    await db_session.commit()

    with _patch_preview_session(db_session):
        resp = await api_client.get(_make_preview_url(trigger.id))
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Hello preview!" in resp.text


@pytest.mark.asyncio
async def test_preview_invalid_token(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/triggers/{trigger.id}/preview?token=invalid")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_preview_missing_token(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/triggers/{trigger.id}/preview")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_preview_empty_token(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/triggers/{trigger.id}/preview?token=")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_preview_nonexistent_trigger(api_client: AsyncClient, db_session: AsyncSession):
    trigger_id = 999999
    token = generate_preview_token(trigger_id)

    with _patch_preview_session(db_session):
        resp = await api_client.get(f"/api/v1/triggers/{trigger_id}/preview?token={token}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_preview_wrong_trigger_id_token(api_client: AsyncClient, db_session: AsyncSession):
    """Token generated for trigger 1 should not work for trigger 2."""
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    other_token = generate_preview_token(trigger.id + 1)
    resp = await api_client.get(f"/api/v1/triggers/{trigger.id}/preview?token={other_token}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_preview_trigger_with_caption(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session, chat.id, content={"caption": "A photo caption"}
    )
    await db_session.commit()

    with _patch_preview_session(db_session):
        resp = await api_client.get(_make_preview_url(trigger.id))
    assert resp.status_code == 200
    assert "A photo caption" in resp.text


@pytest.mark.asyncio
async def test_preview_trigger_with_empty_content(api_client: AsyncClient, db_session: AsyncSession):
    """Trigger with no text/caption should still render (just no text content)."""
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, content={})
    await db_session.commit()

    with _patch_preview_session(db_session):
        resp = await api_client.get(_make_preview_url(trigger.id))
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_preview_no_auth_required(api_client: AsyncClient, db_session: AsyncSession):
    """Preview endpoint uses HMAC token, not standard auth."""
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, content={"text": "Public preview"})
    await db_session.commit()

    with _patch_preview_session(db_session):
        resp = await api_client.get(_make_preview_url(trigger.id))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_preview_trigger_with_buttons(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    content = {
        "text": "Click below",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "Visit", "url": "https://example.com"}]
            ]
        },
    }
    trigger = await create_trigger(db_session, chat.id, content=content)
    await db_session.commit()

    with _patch_preview_session(db_session):
        resp = await api_client.get(_make_preview_url(trigger.id))
    assert resp.status_code == 200
    assert "Visit" in resp.text


@pytest.mark.asyncio
async def test_preview_shows_trigger_id_in_title(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, content={"text": "x"})
    await db_session.commit()

    with _patch_preview_session(db_session):
        resp = await api_client.get(_make_preview_url(trigger.id))
    assert resp.status_code == 200
    assert f"Trigger #{trigger.id}" in resp.text
