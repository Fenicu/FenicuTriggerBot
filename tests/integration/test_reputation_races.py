"""Регрессия гонок репутации: параллельные начисления не должны теряться."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.chat import Chat
from app.db.models.reputation_log import ReputationLog
from app.db.models.user_chat import UserChat
from app.services.reputation_service import add_message_score, add_reaction_score
from tests.factories import create_chat, create_user


async def _seed(factory):
    async with factory() as session:
        chat = await create_chat(session, tags_enabled=True)
        author = await create_user(session)
        fan = await create_user(session)
        session.add(UserChat(user_id=author.id, chat_id=chat.id, is_active=True, reputation_score=0))
        await session.commit()
        return chat.id, author.id, fan.id


async def test_concurrent_reactions_keep_both_points(_async_engine):
    factory = async_sessionmaker(_async_engine, expire_on_commit=False)
    chat_id, author_id, fan_id = await _seed(factory)

    async def react():
        async with factory() as session:
            chat = await session.get(Chat, chat_id)
            await add_reaction_score(session, chat, fan_id, author_id, chat_id)
            await session.commit()

    await asyncio.gather(react(), react())

    async with factory() as session:
        score = await session.scalar(
            select(UserChat.reputation_score).where(UserChat.user_id == author_id, UserChat.chat_id == chat_id)
        )
        chat = await session.get(Chat, chat_id)
        log_count = await session.scalar(
            select(ReputationLog.count).where(
                ReputationLog.chat_id == chat_id,
                ReputationLog.to_user_id == author_id,
            )
        )

    assert score == 2 * chat.tags_weight_reactions
    assert log_count == 2


async def test_concurrent_messages_keep_both_points(_async_engine):
    factory = async_sessionmaker(_async_engine, expire_on_commit=False)
    chat_id, author_id, _ = await _seed(factory)

    async def message():
        async with factory() as session:
            chat = await session.get(Chat, chat_id)
            user_chat = await session.get(UserChat, (author_id, chat_id))
            await add_message_score(session, user_chat, chat)
            await session.commit()

    await asyncio.gather(message(), message())

    async with factory() as session:
        chat = await session.get(Chat, chat_id)
        row = (
            await session.execute(
                select(UserChat.reputation_score, UserChat.daily_message_count).where(
                    UserChat.user_id == author_id, UserChat.chat_id == chat_id
                )
            )
        ).one()

    assert row.reputation_score == 2 * chat.tags_weight_messages
    assert row.daily_message_count == 2
