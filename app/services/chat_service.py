from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat


async def get_or_create_chat(session: AsyncSession, chat_id: int) -> Chat:
    """Получить чат по ID или создать, если он не существует."""
    chat = await session.get(Chat, chat_id)
    if not chat:
        chat = Chat(id=chat_id)
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
    return chat


async def update_chat_settings(session: AsyncSession, chat_id: int, **kwargs) -> Chat:
    """Обновить настройки чата."""
    chat = await get_or_create_chat(session, chat_id)
    for key, value in kwargs.items():
        if hasattr(chat, key):
            setattr(chat, key, value)
    await session.commit()
    await session.refresh(chat)
    return chat


async def update_language(session: AsyncSession, chat_id: int, language_code: str) -> Chat:
    """Обновить язык чата."""
    return await update_chat_settings(session, chat_id, language_code=language_code)
