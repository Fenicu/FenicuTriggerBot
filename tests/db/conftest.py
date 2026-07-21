"""Fixtures для tests/db — родительские строки FK и т.п."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Base
from app.db.models.chat import Chat
from app.db.models.user import User


@pytest_asyncio.fixture
async def base_rows(_async_engine):
    """
    Родительские chat/user строки для FK captcha-сессий.

    chat_id=-100500, user_id∈{42, 43}. Чистит за собой все таблицы после теста —
    нужно тестам, которые не используют db_session (например, конкурентный claim
    с двумя независимыми AsyncSession).
    """
    factory = async_sessionmaker(_async_engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Chat(id=-100500), User(id=42), User(id=43)])
        await session.commit()

    yield

    async with _async_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
