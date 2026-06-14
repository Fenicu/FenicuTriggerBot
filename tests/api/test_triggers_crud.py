"""Тесты CRUD эндпоинтов POST/PATCH /api/v1/triggers/."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from app.db.models.trigger import ModerationStatus
from app.db.models.user import User
from tests.factories import create_chat, create_trigger, create_user


def _admin_headers(user_id: int) -> dict[str, str]:
    token = create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_admin(session: AsyncSession, *, moderator: bool = True) -> int:
    user = await create_user(session, is_bot_moderator=moderator)
    await session.commit()
    return user.id


# ---------------------------------------------------------------------------
# POST /triggers/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_trigger_minimal(api_client: AsyncClient, db_session: AsyncSession):
    """Создание триггера с минимальными полями возвращает 201."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await db_session.commit()

    payload = {
        "chat_id": chat.id,
        "key_phrase": "hello",
        "content": {"text": "world"},
    }
    resp = await api_client.post("/api/v1/triggers/", json=payload, headers=_admin_headers(admin_id))
    assert resp.status_code == 201
    body = resp.json()
    assert body["key_phrase"] == "hello"
    assert body["rich"] is False
    assert body["is_template"] is False
    assert body["preview_url"] is not None


@pytest.mark.asyncio
async def test_create_trigger_rich(api_client: AsyncClient, db_session: AsyncSession):
    """rich=True форсирует is_template=True, возвращает 201."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await db_session.commit()

    payload = {
        "chat_id": chat.id,
        "key_phrase": "rich trigger",
        "content": {"text": "<b>hello</b>"},
        "rich": True,
    }
    resp = await api_client.post("/api/v1/triggers/", json=payload, headers=_admin_headers(admin_id))
    assert resp.status_code == 201
    body = resp.json()
    assert body["rich"] is True
    assert body["is_template"] is True


@pytest.mark.asyncio
async def test_create_trigger_invalid_rich_html(api_client: AsyncClient, db_session: AsyncSession):
    """rich=True с невалидным HTML возвращает 422."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await db_session.commit()

    payload = {
        "chat_id": chat.id,
        "key_phrase": "bad rich",
        "content": {"text": "<script>alert(1)</script>"},
        "rich": True,
    }
    resp = await api_client.post("/api/v1/triggers/", json=payload, headers=_admin_headers(admin_id))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_trigger_nonexistent_chat(api_client: AsyncClient, db_session: AsyncSession):
    """Несуществующий chat_id возвращает 404."""
    admin_id = await _seed_admin(db_session)

    payload = {
        "chat_id": -9999999999999,
        "key_phrase": "test",
        "content": {"text": "hi"},
    }
    resp = await api_client.post("/api/v1/triggers/", json=payload, headers=_admin_headers(admin_id))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_trigger_invalid_regex(api_client: AsyncClient, db_session: AsyncSession):
    """Невалидное regex выражение возвращает 422."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    await db_session.commit()

    payload = {
        "chat_id": chat.id,
        "key_phrase": "[invalid regex",
        "content": {"text": "x"},
        "match_type": "regexp",
    }
    resp = await api_client.post("/api/v1/triggers/", json=payload, headers=_admin_headers(admin_id))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_trigger_unauthenticated(api_client: AsyncClient, db_session: AsyncSession):
    """Без токена — 401."""
    chat = await create_chat(db_session)
    await db_session.commit()

    payload = {"chat_id": chat.id, "key_phrase": "hi", "content": {"text": "x"}}
    resp = await api_client.post("/api/v1/triggers/", json=payload)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /triggers/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_trigger_plain_to_rich(api_client: AsyncClient, db_session: AsyncSession):
    """Обновление plain → rich; is_template тоже становится True."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    payload = {
        "content": {"text": "<b>updated</b>"},
        "rich": True,
    }
    resp = await api_client.patch(
        f"/api/v1/triggers/{trigger.id}", json=payload, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rich"] is True
    assert body["is_template"] is True


@pytest.mark.asyncio
async def test_update_trigger_invalid_rich_html(api_client: AsyncClient, db_session: AsyncSession):
    """PATCH с невалидным rich HTML → 422."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    payload = {
        "content": {"text": "<script>evil()</script>"},
        "rich": True,
    }
    resp = await api_client.patch(
        f"/api/v1/triggers/{trigger.id}", json=payload, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_trigger_not_found(api_client: AsyncClient, db_session: AsyncSession):
    """PATCH несуществующего trigger_id → 404."""
    admin_id = await _seed_admin(db_session)

    resp = await api_client.patch(
        "/api/v1/triggers/9999999", json={"key_phrase": "new"}, headers=_admin_headers(admin_id)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_trigger_null_content_ignored(api_client: AsyncClient, db_session: AsyncSession):
    """Явный null в поле content — игнорируется, не вызывает 500."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()

    payload = {"content": None, "key_phrase": "updated"}
    resp = await api_client.patch(
        f"/api/v1/triggers/{trigger.id}", json=payload, headers=_admin_headers(admin_id)
    )
    # null игнорируется — обновляется только key_phrase
    assert resp.status_code == 200
    assert resp.json()["key_phrase"] == "updated"


@pytest.mark.asyncio
async def test_update_trigger_key_phrase_only(api_client: AsyncClient, db_session: AsyncSession):
    """Обновление только key_phrase — остальные поля не меняются."""
    admin_id = await _seed_admin(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, key_phrase="original")
    await db_session.commit()

    resp = await api_client.patch(
        f"/api/v1/triggers/{trigger.id}",
        json={"key_phrase": "changed"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["key_phrase"] == "changed"
    assert body["preview_url"] is not None


# ---------------------------------------------------------------------------
# PATCH /triggers/{id} — re-moderation branch
#
# Находка: get_current_admin требует is_bot_moderator=True ИЛИ id in BOT_ADMINS.
# _skip_moderation = is_trusted OR is_bot_moderator OR id in BOT_ADMINS.
# Любой пользователь, прошедший get_current_admin, автоматически попадает в
# _skip_moderation → re-moderation ветка недостижима через обычный HTTP-flow
# (без override зависимости).
#
# Тесты ниже используют dependency_override для get_current_admin, подставляя
# пользователя с is_bot_moderator=False / is_trusted=False напрямую, чтобы
# покрыть endpoint-логику независимо от механизма авторизации.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def _api_client_with_override(db_session: AsyncSession):
    """Возвращает фабрику клиентов с кастомным override для get_current_admin."""
    from app.api.v1.router import api_router
    from app.api.deps import get_current_admin
    from app.core.database import get_db
    from fastapi import FastAPI

    def make_client(admin_user: User) -> AsyncClient:
        test_app = FastAPI()
        test_app.include_router(api_router, prefix="/api/v1")

        async def _override_db():
            yield db_session

        async def _override_admin():
            return admin_user

        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_admin] = _override_admin

        transport = ASGITransport(app=test_app)
        return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)

    return make_client


@pytest.mark.asyncio
async def test_patch_content_by_regular_admin_requeues_moderation(
    _api_client_with_override, db_session: AsyncSession
):
    """PATCH content обычным (не skip) админом → moderation_status становится PENDING."""
    # Создаём пользователя без is_bot_moderator и is_trusted
    regular_admin = await create_user(db_session, is_bot_moderator=False, is_trusted=False)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE)
    await db_session.commit()

    make_client = _api_client_with_override
    async with make_client(regular_admin) as client:
        resp = await client.patch(
            f"/api/v1/triggers/{trigger.id}",
            json={"content": {"text": "new content"}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["moderation_status"] == ModerationStatus.PENDING


@pytest.mark.asyncio
async def test_patch_content_by_trusted_admin_keeps_status(
    _api_client_with_override, db_session: AsyncSession
):
    """PATCH content доверенным (skip) админом → moderation_status остаётся SAFE."""
    trusted_admin = await create_user(db_session, is_bot_moderator=True, is_trusted=False)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE)
    await db_session.commit()

    make_client = _api_client_with_override
    async with make_client(trusted_admin) as client:
        resp = await client.patch(
            f"/api/v1/triggers/{trigger.id}",
            json={"content": {"text": "trusted update"}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["moderation_status"] == ModerationStatus.SAFE


@pytest.mark.asyncio
async def test_patch_non_content_field_by_regular_admin_no_requeue(
    _api_client_with_override, db_session: AsyncSession
):
    """PATCH НЕ content поля (is_case_sensitive) обычным админом → статус не меняется."""
    regular_admin = await create_user(db_session, is_bot_moderator=False, is_trusted=False)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.SAFE)
    await db_session.commit()

    make_client = _api_client_with_override
    async with make_client(regular_admin) as client:
        resp = await client.patch(
            f"/api/v1/triggers/{trigger.id}",
            json={"is_case_sensitive": True},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["moderation_status"] == ModerationStatus.SAFE
    assert body["is_case_sensitive"] is True
