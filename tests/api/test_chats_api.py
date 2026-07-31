"""Tests for /api/v1/chats/ endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from tests.factories import create_banned_chat, create_chat, create_trigger, create_user


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
# GET /chats/  (list)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_chats_empty(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get("/api/v1/chats/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_list_chats_returns_items(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_chat(db_session, title="Chat A", type="supergroup")
    await create_chat(db_session, title="Chat B", type="supergroup")
    await db_session.commit()

    resp = await api_client.get("/api/v1/chats/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 2
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_list_chats_pagination(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    for i in range(5):
        await create_chat(db_session, title=f"Chat {i}", type="supergroup")
    await db_session.commit()

    resp = await api_client.get("/api/v1/chats/", params={"page": 1, "limit": 2}, headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 5
    assert len(body["items"]) == 2
    assert body["pagination"]["total_pages"] == 3


@pytest.mark.asyncio
async def test_list_chats_search_by_title(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_chat(db_session, title="Alpha Group", type="supergroup")
    await create_chat(db_session, title="Beta Group", type="supergroup")
    await db_session.commit()

    resp = await api_client.get("/api/v1/chats/", params={"query": "Alpha"}, headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["title"] == "Alpha Group"


@pytest.mark.asyncio
async def test_list_chats_excludes_private_by_default(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_chat(db_session, title="Public", type="supergroup")
    await create_chat(db_session, title="Private", type="private")
    await db_session.commit()

    resp = await api_client.get("/api/v1/chats/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 1

    resp2 = await api_client.get("/api/v1/chats/", params={"include_private": True}, headers=_admin_headers(admin_id))
    assert resp2.status_code == 200
    assert resp2.json()["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_list_chats_filter_is_active(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_chat(db_session, title="Active", type="supergroup", is_active=True)
    await create_chat(db_session, title="Inactive", type="supergroup", is_active=False)
    await db_session.commit()

    resp = await api_client.get("/api/v1/chats/", params={"is_active": True}, headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 1
    assert resp.json()["items"][0]["title"] == "Active"


@pytest.mark.asyncio
async def test_list_chats_filter_is_banned(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat1 = await create_chat(db_session, title="Clean", type="supergroup")
    chat2 = await create_chat(db_session, title="Banned", type="supergroup")
    await create_banned_chat(db_session, chat2.id, reason="spam")
    await db_session.commit()

    resp = await api_client.get("/api/v1/chats/", params={"is_banned": True}, headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["title"] == "Banned"
    assert body["items"][0]["is_banned"] is True
    assert body["items"][0]["ban_reason"] == "spam"


@pytest.mark.asyncio
async def test_list_chats_with_triggers_count(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await create_trigger(db_session, chat.id)
    await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get("/api/v1/chats/", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["items"][0]["triggers_count"] == 2


@pytest.mark.asyncio
async def test_list_chats_unauthenticated(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/chats/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /chats/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_chat_by_id(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, title="My Chat", type="supergroup")
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/chats/{chat.id}", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == chat.id
    assert body["title"] == "My Chat"


@pytest.mark.asyncio
async def test_get_chat_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get("/api/v1/chats/-999999999999", headers=_admin_headers(admin_id))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Chat not found"


@pytest.mark.asyncio
async def test_get_chat_shows_ban_status(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await create_banned_chat(db_session, chat.id, reason="violations")
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/chats/{chat.id}", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_banned"] is True
    assert body["ban_reason"] == "violations"


# ---------------------------------------------------------------------------
# POST /chats/{id}/trust
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_trust(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, is_trusted=False, type="supergroup")
    await db_session.commit()

    resp = await api_client.post(f"/api/v1/chats/{chat.id}/trust", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["is_trusted"] is True

    # Toggle back
    resp2 = await api_client.post(f"/api/v1/chats/{chat.id}/trust", headers=_admin_headers(admin_id))
    assert resp2.status_code == 200
    assert resp2.json()["is_trusted"] is False


@pytest.mark.asyncio
async def test_toggle_trust_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.post("/api/v1/chats/-999999999999/trust", headers=_admin_headers(admin_id))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_toggle_trust_resets_trust_auto_granted_on_manual_grant(
    api_client: AsyncClient, db_session: AsyncSession
):
    """Ручное включение доверия через API должно сбрасывать trust_auto_granted в False.

    Иначе флаг "выдано автоматикой" переживает ручной toggle, и первый же flagged-исход
    снимет уже ЧЕЛОВЕЧЕСКОЕ доверие вопреки заявленной семантике (см. defect #5 ревью).
    """
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, is_trusted=False, type="supergroup")
    await db_session.commit()

    resp = await api_client.post(f"/api/v1/chats/{chat.id}/trust", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_trusted"] is True

    await db_session.refresh(chat)
    assert chat.trust_auto_granted is False


@pytest.mark.asyncio
async def test_toggle_trust_resets_trust_auto_granted_when_revoking_auto_grant(
    api_client: AsyncClient, db_session: AsyncSession
):
    """Ручное выключение АВТО-выданного доверия тоже сбрасывает trust_auto_granted.

    Сценарий из ревью: модератор выключил авто-выданное доверие руками, потом включил
    обратно -- trust_auto_granted не должен «пережить» этот цикл (см. defect #5).
    """
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, is_trusted=True, trust_auto_granted=True, type="supergroup")
    await db_session.commit()

    # Ручное выключение
    resp = await api_client.post(f"/api/v1/chats/{chat.id}/trust", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["is_trusted"] is False

    await db_session.refresh(chat)
    assert chat.trust_auto_granted is False

    # Ручное включение обратно -- остаётся ручным, не авто
    resp2 = await api_client.post(f"/api/v1/chats/{chat.id}/trust", headers=_admin_headers(admin_id))
    assert resp2.status_code == 200
    assert resp2.json()["is_trusted"] is True

    await db_session.refresh(chat)
    assert chat.trust_auto_granted is False


# ---------------------------------------------------------------------------
# PATCH /chats/{id}/settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_chat_settings(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/chats/{chat.id}/settings",
        json={"timezone": "Europe/Moscow", "module_triggers": False},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "Europe/Moscow"
    assert body["module_triggers"] is False


@pytest.mark.asyncio
async def test_update_chat_settings_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.patch(
        "/api/v1/chats/-999999999999/settings",
        json={"module_triggers": True},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /chats/{id}/ban
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ban_chat(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/chats/{chat.id}/ban",
        json={"reason": "Spam detected"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_banned"] is True
    assert body["ban_reason"] == "Spam detected"


@pytest.mark.asyncio
async def test_ban_chat_not_found(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.post(
        "/api/v1/chats/-999999999999/ban",
        json={"reason": "spam"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ban_chat_missing_reason_422(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.post(
        f"/api/v1/chats/{chat.id}/ban",
        json={},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /chats/{id}/leave
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leave_chat(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.post("/api/v1/chats/-1001234567890/leave", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /chats/{id}/message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    resp = await api_client.post(
        "/api/v1/chats/-1001234567890/message",
        json={"text": "Hello!"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# GET /chats/{id}/triggers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_chat_triggers(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await create_trigger(db_session, chat.id, key_phrase="t1")
    await create_trigger(db_session, chat.id, key_phrase="t2")
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/chats/{chat.id}/triggers", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 2
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_list_chat_triggers_empty(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session, type="supergroup")
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/chats/{chat.id}/triggers", headers=_admin_headers(admin_id))
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# Sorting by various fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_chats_sort_by_title(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    await create_chat(db_session, title="Zebra", type="supergroup")
    await create_chat(db_session, title="Apple", type="supergroup")
    await db_session.commit()

    resp = await api_client.get(
        "/api/v1/chats/",
        params={"sort_by": "title", "sort_order": "asc"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["title"] == "Apple"
    assert items[1]["title"] == "Zebra"
