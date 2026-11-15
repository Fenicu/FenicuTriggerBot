"""Кэш триггеров чата: порядок, состав полей, инвалидация."""

from sqlalchemy import update

from app.db.models.trigger import Trigger
from app.services import trigger_service
from tests.factories import create_chat, create_trigger


async def test_get_triggers_by_chat_is_ordered_by_id(db_session):
    chat = await create_chat(db_session)
    first = await create_trigger(db_session, chat_id=chat.id, key_phrase="k1")
    second = await create_trigger(db_session, chat_id=chat.id, key_phrase="k2")
    third = await create_trigger(db_session, chat_id=chat.id, key_phrase="k3")
    await db_session.commit()
    # UPDATE переносит строку в конец кучи: без ORDER BY первый триггер вернулся бы последним
    await db_session.execute(update(Trigger).where(Trigger.id == first.id).values(key_phrase="k1 renamed"))
    await db_session.commit()

    triggers = await trigger_service.get_triggers_by_chat(db_session, chat.id)

    assert [t.id for t in triggers] == [first.id, second.id, third.id]
