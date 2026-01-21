from sqlalchemy import String, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models.chat import BannedChat, Chat
from app.db.models.trigger import Trigger
from app.db.models.user_chat import UserChat


async def get_chats(
    session: AsyncSession,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
    include_private: bool = False,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    is_active: bool | None = None,
    is_trusted: bool | None = None,
    is_banned: bool | None = None,
    chat_type: str | None = None,
) -> tuple[list[tuple[Chat, BannedChat | None, int, int]], int]:
    """Получает список чатов с пагинацией и поиском."""
    triggers_count_subquery = select(func.count(Trigger.id)).where(Trigger.chat_id == Chat.id).scalar_subquery()

    users_count_subquery = (
        select(func.count(UserChat.user_id))
        .where(UserChat.chat_id == Chat.id)
        .where(UserChat.is_active.is_(True))
        .scalar_subquery()
    )

    stmt = select(Chat, BannedChat, triggers_count_subquery, users_count_subquery).outerjoin(
        BannedChat, Chat.id == BannedChat.chat_id
    )
    if query:
        stmt = stmt.where(cast(Chat.id, String).ilike(f"%{query}%") | Chat.title.ilike(f"%{query}%"))

    if not include_private:
        stmt = stmt.where((Chat.type != "private") | (Chat.type.is_(None)))

    if is_active is not None:
        stmt = stmt.where(Chat.is_active == is_active)

    if is_trusted is not None:
        stmt = stmt.where(Chat.is_trusted == is_trusted)

    if is_banned is True:
        stmt = stmt.where(BannedChat.chat_id.isnot(None))
    elif is_banned is False:
        stmt = stmt.where(BannedChat.chat_id.is_(None))

    if chat_type:
        stmt = stmt.where(Chat.type == chat_type)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    sort_column = getattr(Chat, sort_by, Chat.created_at)
    stmt = stmt.order_by(sort_column.asc()) if sort_order == "asc" else stmt.order_by(sort_column.desc())

    stmt = stmt.offset((page - 1) * limit).limit(limit)
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
    is_active: bool | None = None,
) -> Chat:
    """Получить чат по ID или создать, если он не существует. Обновляет данные."""
    values = {
        "id": chat_id,
        "title": title,
        "username": username,
        "type": type,
        "description": description,
        "invite_link": invite_link,
        "photo_id": photo_id,
    }
    if is_active is not None:
        values["is_active"] = is_active

    set_ = {
        "title": title,
        "username": username,
        "type": type,
        "description": description,
        "invite_link": invite_link,
        "photo_id": photo_id,
        "updated_at": func.now(),
    }
    if is_active is not None:
        set_["is_active"] = is_active

    stmt = (
        insert(Chat)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[Chat.id],
            set_=set_,
        )
        .returning(Chat)
    )
    result = await session.execute(stmt)
    await session.commit()
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


async def update_chat_settings_specific(
    session: AsyncSession,
    chat_id: int,
    timezone: str | None = None,
    module_triggers: bool | None = None,
    module_moderation: bool | None = None,
) -> Chat:
    """Обновить специфические настройки чата: timezone, module_triggers, module_moderation."""
    kwargs = {}
    if timezone is not None:
        kwargs["timezone"] = timezone
    if module_triggers is not None:
        kwargs["module_triggers"] = module_triggers
    if module_moderation is not None:
        kwargs["module_moderation"] = module_moderation
    return await update_chat_settings(session, chat_id, **kwargs)


async def update_language(session: AsyncSession, chat_id: int, language_code: str) -> Chat:
    """Обновить язык чата."""
    return await update_chat_settings(session, chat_id, language_code=language_code)


async def get_chat_users(
    session: AsyncSession,
    chat_id: int,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[UserChat], int]:
    """Получает список пользователей чата."""
    stmt = select(UserChat).options(joinedload(UserChat.user)).where(UserChat.chat_id == chat_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(UserChat.updated_at.desc())
    result = await session.execute(stmt)
    chat_users = result.scalars().all()

    return chat_users, total
