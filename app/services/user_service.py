from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.db.models.user import User
from app.db.models.user_chat import UserChat


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language_code: str | None = None,
    is_premium: bool | None = None,
) -> User:
    """
    Получает пользователя из базы данных или создает нового.
    Также обновляет информацию о пользователе.
    """
    stmt = (
        insert(User)
        .values(
            id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            is_premium=is_premium,
        )
        .on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language_code": language_code,
                "is_premium": is_premium,
                "updated_at": func.now(),
            },
        )
        .returning(User)
    )
    result = await session.execute(stmt)
    await session.commit()
    user = result.scalar_one()

    if user_id in settings.BOT_ADMINS:
        user.is_bot_moderator = True
        user.is_trusted = True

    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    """Получает пользователя по ID."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user and user_id in settings.BOT_ADMINS:
        user.is_bot_moderator = True
        user.is_trusted = True

    return user


async def get_users(
    session: AsyncSession,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    is_premium: bool | None = None,
    is_trusted: bool | None = None,
    is_bot_moderator: bool | None = None,
) -> tuple[list[User], int]:
    """Получает список пользователей с пагинацией и поиском."""
    stmt = select(User)
    if query:
        stmt = stmt.where(
            or_(
                User.username.ilike(f"%{query}%"),
                User.first_name.ilike(f"%{query}%"),
                User.last_name.ilike(f"%{query}%"),
                cast(User.id, String).ilike(f"%{query}%"),
            )
        )

    if is_premium is not None:
        stmt = stmt.where(User.is_premium == is_premium)

    if is_trusted is not None:
        stmt = stmt.where(User.is_trusted == is_trusted)

    if is_bot_moderator is not None:
        stmt = stmt.where(User.is_bot_moderator == is_bot_moderator)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    sort_column = getattr(User, sort_by, User.created_at)
    stmt = stmt.order_by(sort_column.asc()) if sort_order == "asc" else stmt.order_by(sort_column.desc())

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await session.execute(stmt)
    users = result.scalars().all()

    final_users = []
    for user in users:
        if user.id in settings.BOT_ADMINS:
            user.is_bot_moderator = True
            user.is_trusted = True
        final_users.append(user)

    return final_users, total


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """Получает пользователя по username."""
    username = username.lstrip("@")
    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user and user.id in settings.BOT_ADMINS:
        user.is_bot_moderator = True
        user.is_trusted = True

    return user


async def get_user_chats(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[UserChat], int]:
    """Получает список чатов пользователя."""
    stmt = select(UserChat).options(joinedload(UserChat.chat)).where(UserChat.user_id == user_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(UserChat.updated_at.desc())
    result = await session.execute(stmt)
    user_chats = result.scalars().all()

    return user_chats, total
