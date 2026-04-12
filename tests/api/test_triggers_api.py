"""Tests for /api/v1/triggers/ endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from app.db.models.trigger import ModerationStatus
from tests.factories import create_chat, create_trigger, create_user, create_banned_chat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_headers(user_id: int) -> dict[str, str]:
    """Build Authorization header with a valid Bearer token."""
    token = create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_admin(session: AsyncSession, *, moderator: bool = True) -> int:
    """Create an admin/moderator user and return its id."""
    user = await create_user(session, is_bot_moderator=moderator)
    await session.commit()
    return user.id


# ---------------------------------------------------------------------------
# GET /triggers/  (list + filter)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_triggers_empty(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get("/api/v1/triggers/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_triggers_returns_items(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id)
    await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get("/api/v1/triggers/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_list_triggers_filter_by_status(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.PENDING)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.FLAGGED)
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/triggers/", params={"status": "pending"}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["moderation_status"] == "pending"


@pytest.mark.asyncio
async def test_list_triggers_search(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id, key_phrase="hello_world")
    await create_trigger(db_session, chat.id, key_phrase="goodbye")
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/triggers/", params={"search": "hello"}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert "hello" in body["items"][0]["key_phrase"]


@pytest.mark.asyncio
async def test_list_triggers_pagination(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    for _ in range(5):
        await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/triggers/", params={"page": 1, "limit": 2}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2

    resp2 = await api_client.get(
        "/api/v1/triggers/", params={"page": 3, "limit": 2}, headers=_admin_headers(admin_id)
    )
    assert resp2.status_code == 200
    assert len(resp2.json()["items"]) == 1


@pytest.mark.asyncio
async def test_list_triggers_sorting_asc(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id, key_phrase="alpha")
    await create_trigger(db_session, chat.id, key_phrase="beta")
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/triggers/",
        params={"sort_by": "key_phrase", "order": "asc"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["key_phrase"] == "alpha"
    assert items[1]["key_phrase"] == "beta"


@pytest.mark.asyncio
async def test_list_triggers_excludes_soft_deleted(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id)
    await create_trigger(db_session, chat.id, is_deleted=True)
    await db_session.commit()

    resp = await api_client.get("/api/v1/triggers/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_triggers_excludes_banned_chat(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id)
    await create_banned_chat(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get("/api/v1/triggers/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_triggers_filter_by_chat_id(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat1 = await create_chat(db_session)
    chat2 = await create_chat(db_session)
    await create_trigger(db_session, chat1.id)
    await create_trigger(db_session, chat2.id)
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/triggers/", params={"chat_id": chat1.id}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["chat_id"] == chat1.id


@pytest.mark.asyncio
async def test_list_triggers_invalid_status_422(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get(
        "/api/v1/triggers/", params={"status": "invalid"}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_triggers_unauthenticated(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/triggers/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /triggers/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trigger_by_id(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/triggers/{trigger.id}", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == trigger.id
    assert body["key_phrase"] == trigger.key_phrase
    assert body["chat_title"] == chat.title
    assert body["preview_url"] is not None


@pytest.mark.asyncio
async def test_get_trigger_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get("/api/v1/triggers/999999", headers=_admin_headers(admin_id))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Trigger not found"


# ---------------------------------------------------------------------------
# POST /triggers/{id}/approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_trigger(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session, chat.id, moderation_status=ModerationStatus.PENDING
    )
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/triggers/{trigger.id}/approve", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["moderation_status"] == "safe"
    assert "Manual Approve" in body["moderation_reason"]


@pytest.mark.asyncio
async def test_approve_trigger_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.post(
        "/api/v1/triggers/999999/approve", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /triggers/{id}/requeue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requeue_trigger(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session, chat.id, moderation_status=ModerationStatus.SAFE
    )
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/triggers/{trigger.id}/requeue", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    assert resp.json()["moderation_status"] == "pending"


@pytest.mark.asyncio
async def test_requeue_trigger_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.post(
        "/api/v1/triggers/999999/requeue", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /triggers/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_trigger(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.delete(
        f"/api/v1/triggers/{trigger.id}", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify it no longer appears in the list
    resp2 = await api_client.get("/api/v1/triggers/", headers=_admin_headers(admin_id))
    assert resp2.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_trigger_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.delete(
        "/api/v1/triggers/999999", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /triggers/{id}/moderation-history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderation_history_empty(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get(
        f"/api/v1/triggers/{trigger.id}/moderation-history",
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["current_step"] == "created"


@pytest.mark.asyncio
async def test_moderation_history_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get(
        "/api/v1/triggers/999999/moderation-history",
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /triggers/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_stats_empty(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get("/api/v1/triggers/stats", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["safe"] == 0
    assert body["pending"] == 0
    assert body["flagged"] == 0
    assert body["banned"] == 0
    assert body["error"] == 0


@pytest.mark.asyncio
async def test_trigger_stats_counts(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.PENDING)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.FLAGGED)
    await db_session.commit()

    resp = await api_client.get("/api/v1/triggers/stats", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["safe"] == 2
    assert body["pending"] == 1
    assert body["flagged"] == 1


@pytest.mark.asyncio
async def test_trigger_stats_excludes_deleted(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE)
    await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE, is_deleted=True)
    await db_session.commit()

    resp = await api_client.get("/api/v1/triggers/stats", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["safe"] == 1


# ---------------------------------------------------------------------------
# GET /triggers/{id}/queue-status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_status(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get(
        "/api/v1/triggers/123/queue-status", headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    # Valkey is mocked to return 0 for exists, so not processing
    assert resp.json()["is_processing"] is False
