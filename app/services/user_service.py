from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
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
        )
        .on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
        )
        .returning(User)
    )
    result = await session.execute(stmt)
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

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(User.created_at.desc())
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
