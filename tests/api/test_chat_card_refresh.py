"""Карточка чата в админке обновляется из getChat: убранные описание/ссылка/фото очищаются."""

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from app.db.models.chat import Chat
from tests.factories import create_chat, create_user


async def _headers(db_session: AsyncSession) -> dict[str, str]:
    admin = await create_user(db_session, is_bot_moderator=True)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_auth_token(admin.id)}"}


async def _stored(db_session: AsyncSession, chat_id: int) -> Chat:
    db_session.expire_all()
    return (await db_session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()


def _tg_chat(**fields) -> MagicMock:
    defaults = {"title": "T", "username": None, "type": "supergroup", "description": None, "invite_link": None}
    return MagicMock(photo=None, **{**defaults, **fields})


async def test_read_chat_clears_fields_removed_in_telegram(api_client: AsyncClient, db_session: AsyncSession):
    headers = await _headers(db_session)
    chat = await create_chat(db_session, title="T", description="old about", invite_link="old_link", photo_id="old")
    await db_session.commit()

    with patch("app.api.v1.endpoints.chats.bot") as mock_bot:
        mock_bot.get_chat = AsyncMock(return_value=_tg_chat())
        resp = await api_client.get(f"/api/v1/chats/{chat.id}", headers=headers)

    assert resp.status_code == 200
    stored = await _stored(db_session, chat.id)
    assert stored.description is None
    assert stored.invite_link is None
    assert stored.photo_id is None


async def test_read_chat_stores_fields_present_in_telegram(api_client: AsyncClient, db_session: AsyncSession):
    headers = await _headers(db_session)
    chat = await create_chat(db_session, title="T")
    await db_session.commit()

    with patch("app.api.v1.endpoints.chats.bot") as mock_bot:
        mock_bot.get_chat = AsyncMock(return_value=_tg_chat(description="about", invite_link="link"))
        resp = await api_client.get(f"/api/v1/chats/{chat.id}", headers=headers)

    assert resp.status_code == 200
    stored = await _stored(db_session, chat.id)
    assert stored.description == "about"
    assert stored.invite_link == "link"


async def test_read_chat_keeps_stored_fields_when_telegram_fails(api_client: AsyncClient, db_session: AsyncSession):
    headers = await _headers(db_session)
    chat = await create_chat(db_session, title="T", description="about")
    await db_session.commit()

    with patch("app.api.v1.endpoints.chats.bot") as mock_bot:
        mock_bot.get_chat = AsyncMock(side_effect=RuntimeError("telegram down"))
        resp = await api_client.get(f"/api/v1/chats/{chat.id}", headers=headers)

    assert resp.status_code == 200
    assert (await _stored(db_session, chat.id)).description == "about"
