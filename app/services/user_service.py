from sqlalchemy import select
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
