"""get_or_create_chat: не затирать description/invite_link/photo и не писать в БД на каждом апдейте."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.db.models.chat import Chat
from app.services import chat_service
from tests.factories import create_chat


@pytest.fixture(autouse=True)
def _real_valkey(valkey_client):
    with patch("app.services.chat_service.valkey", valkey_client):
        yield valkey_client


async def _reload(db_session, chat_id: int) -> Chat:
    db_session.expire_all()
    return (await db_session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()


async def _updated_at(db_session, chat_id: int):
    return (await db_session.execute(select(Chat.updated_at).where(Chat.id == chat_id))).scalar_one()


async def test_update_without_extra_fields_keeps_stored_values(db_session):
    """Обычный апдейт не несёт description/invite_link/photo -- сохранённые значения остаются."""
    chat = await create_chat(
        db_session, title="Old", description="About us", invite_link="https://t.me/+abc", photo_id="photo123"
    )
    await db_session.commit()

    await chat_service.get_or_create_chat(db_session, chat_id=chat.id, title="New", type="supergroup")

    stored = await _reload(db_session, chat.id)
    assert stored.title == "New"
    assert stored.description == "About us"
    assert stored.invite_link == "https://t.me/+abc"
    assert stored.photo_id == "photo123"


async def test_present_extra_fields_are_stored(db_session):
    chat = await create_chat(db_session, title="T", description="old", photo_id="old_photo")
    await db_session.commit()

    await chat_service.get_or_create_chat(
        db_session, chat_id=chat.id, title="T", type="supergroup", description="new", photo_id="new_photo"
    )

    stored = await _reload(db_session, chat.id)
    assert stored.description == "new"
    assert stored.photo_id == "new_photo"
    assert stored.invite_link is None


async def test_full_info_clears_removed_fields(db_session):
    """Полная карточка чата (getChat) -- источник истины: отсутствующее поле значит, что его убрали."""
    chat = await create_chat(db_session, title="T", description="old", invite_link="link", photo_id="photo")
    await db_session.commit()

    await chat_service.get_or_create_chat(
        db_session, chat_id=chat.id, title="T", type="supergroup", description="kept", full_info=True
    )

    stored = await _reload(db_session, chat.id)
    assert stored.description == "kept"
    assert stored.invite_link is None
    assert stored.photo_id is None


async def test_unchanged_chat_is_not_written_again(db_session):
    first = await chat_service.get_or_create_chat(db_session, chat_id=-100701, title="T", username="u", type="group")
    before = await _updated_at(db_session, -100701)

    second = await chat_service.get_or_create_chat(db_session, chat_id=-100701, title="T", username="u", type="group")

    assert second.id == first.id
    assert await _updated_at(db_session, -100701) == before


async def test_unchanged_chat_skips_commit(db_session):
    await chat_service.get_or_create_chat(db_session, chat_id=-100702, title="T", type="group")

    with patch.object(db_session, "commit", new_callable=AsyncMock) as mock_commit:
        await chat_service.get_or_create_chat(db_session, chat_id=-100702, title="T", type="group")

    mock_commit.assert_not_awaited()


async def test_skipped_upsert_returns_current_settings(db_session, _async_engine):
    """При пропуске апсерта чат читается из БД -- настройки, изменённые через API, видны сразу."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await chat_service.get_or_create_chat(db_session, chat_id=-100703, title="T", type="group")
    async with async_sessionmaker(_async_engine)() as other:
        await other.execute(update(Chat).where(Chat.id == -100703).values(module_triggers=False))
        await other.commit()
    db_session.expire_all()

    chat = await chat_service.get_or_create_chat(db_session, chat_id=-100703, title="T", type="group")

    assert chat.module_triggers is False


@pytest.mark.parametrize(
    "changed",
    [{"title": "Renamed"}, {"username": "new_username"}, {"type": "supergroup"}],
)
async def test_changed_field_is_written(db_session, changed):
    base = {"title": "T", "username": "u", "type": "group"}
    await chat_service.get_or_create_chat(db_session, chat_id=-100704, **base)

    chat = await chat_service.get_or_create_chat(db_session, chat_id=-100704, **{**base, **changed})

    field, value = next(iter(changed.items()))
    assert getattr(chat, field) == value
    assert getattr(await _reload(db_session, -100704), field) == value


async def test_is_active_is_always_written(db_session):
    await chat_service.get_or_create_chat(db_session, chat_id=-100705, title="T", type="group")

    await chat_service.get_or_create_chat(db_session, chat_id=-100705, title="T", type="group", is_active=False)

    assert (await _reload(db_session, -100705)).is_active is False


async def test_seen_cache_is_short_lived(db_session, _real_valkey):
    await chat_service.get_or_create_chat(db_session, chat_id=-100706, title="T", type="group")

    ttl = await _real_valkey.ttl("chat_seen:-100706")
    assert 0 < ttl <= 600


async def test_missing_row_behind_fresh_cache_is_created(db_session, _real_valkey):
    """Кэш говорит «чат без изменений», а строки в БД нет -- чат создаётся заново."""
    await chat_service.get_or_create_chat(db_session, chat_id=-100707, title="T", type="group")
    await db_session.execute(Chat.__table__.delete().where(Chat.id == -100707))
    await db_session.commit()
    db_session.expire_all()

    chat = await chat_service.get_or_create_chat(db_session, chat_id=-100707, title="T", type="group")

    assert chat.id == -100707
    assert (await _reload(db_session, -100707)).title == "T"


async def test_works_when_valkey_is_down(db_session):
    broken = MagicMock()
    broken.get = AsyncMock(side_effect=ConnectionError("down"))
    broken.set = AsyncMock(side_effect=ConnectionError("down"))

    with patch("app.services.chat_service.valkey", broken):
        await chat_service.get_or_create_chat(db_session, chat_id=-100708, title="T", type="group")
        chat = await chat_service.get_or_create_chat(db_session, chat_id=-100708, title="T2", type="group")

    assert chat.title == "T2"
