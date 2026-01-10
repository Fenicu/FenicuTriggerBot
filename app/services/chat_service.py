from sqlalchemy import String, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import BannedChat, Chat


async def get_chats(
    session: AsyncSession,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
) -> tuple[list[tuple[Chat, BannedChat | None]], int]:
    """Получает список чатов с пагинацией и поиском."""
    stmt = select(Chat, BannedChat).outerjoin(BannedChat, Chat.id == BannedChat.chat_id)
    if query:
        stmt = stmt.where(cast(Chat.id, String).ilike(f"%{query}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(Chat.created_at.desc())
    result = await session.execute(stmt)
    return result.all(), total


async def get_chat_with_ban_status(session: AsyncSession, chat_id: int) -> tuple[Chat | None, BannedChat | None]:
    """Получает чат и статус бана."""
    stmt = select(Chat, BannedChat).outerjoin(BannedChat, Chat.id == BannedChat.chat_id).where(Chat.id == chat_id)
    result = await session.execute(stmt)
    return result.first() or (None, None)


async def ban_chat(session: AsyncSession, chat_id: int, reason: str) -> BannedChat:
    """Банит чат."""
    banned_chat = await session.get(BannedChat, chat_id)
    if not banned_chat:
        banned_chat = BannedChat(chat_id=chat_id, reason=reason)
        session.add(banned_chat)
        await session.commit()
        await session.refresh(banned_chat)
    return banned_chat


async def unban_chat(session: AsyncSession, chat_id: int) -> None:
    """Разбанивает чат."""
    banned_chat = await session.get(BannedChat, chat_id)
    if banned_chat:
        await session.delete(banned_chat)
        await session.commit()


async def get_or_create_chat(
    session: AsyncSession,
    chat_id: int,
    title: str | None = None,
    username: str | None = None,
    type: str | None = None,
    description: str | None = None,
    invite_link: str | None = None,
    photo_id: str | None = None,
) -> Chat:
    """Получить чат по ID или создать, если он не существует. Обновляет данные."""
    stmt = (
        insert(Chat)
        .values(
            id=chat_id,
            title=title,
            username=username,
            type=type,
            description=description,
            invite_link=invite_link,
            photo_id=photo_id,
        )
        .on_conflict_do_update(
            index_elements=[Chat.id],
            set_={
                "title": title,
                "username": username,
                "type": type,
                "description": description,
                "invite_link": invite_link,
                "photo_id": photo_id,
            },
        )
        .returning(Chat)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def update_chat_settings(session: AsyncSession, chat_id: int, **kwargs) -> Chat:
    """Обновить настройки чата."""
    chat = await session.get(Chat, chat_id)
    if not chat:
        chat = Chat(id=chat_id)
        session.add(chat)

    for key, value in kwargs.items():
        if hasattr(chat, key):
            setattr(chat, key, value)
    await session.commit()
    await session.refresh(chat)
    return chat


async def update_language(session: AsyncSession, chat_id: int, language_code: str) -> Chat:
    """Обновить язык чата."""
    return await update_chat_settings(session, chat_id, language_code=language_code)
