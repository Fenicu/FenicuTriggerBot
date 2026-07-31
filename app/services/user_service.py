import logging

from sqlalchemy import ColumnElement, String, and_, case, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, joinedload

from app.core.config import settings
from app.db.models.captcha_session import ChatCaptchaSession
from app.db.models.moderation_history import ModerationHistory
from app.db.models.trigger import Trigger
from app.db.models.trust_history import ChatTrustHistory
from app.db.models.user import User
from app.db.models.user_chat import UserChat
from app.db.models.warn import Warn

logger = logging.getLogger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language_code: str | None = None,
    is_premium: bool | None = None,
    is_bot: bool = False,
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
            is_bot=is_bot,
        )
        .on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language_code": language_code,
                "is_premium": is_premium,
                "is_bot": is_bot,
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


def _flag_filter(column: InstrumentedAttribute[bool], value: bool, admin_ids: list[int]) -> ColumnElement[bool]:
    """Условие для is_trusted/is_bot_moderator с учётом BOT_ADMINS.

    Админы всегда отображаются как trusted/moderator (см. get_users ниже), поэтому
    фильтр по этим флагам должен либо включать их (value=True), либо исключать
    (value=False), а не полагаться только на значение колонки в БД.
    """
    if not admin_ids:
        return column.is_(value)
    if value:
        return or_(column.is_(True), User.id.in_(admin_ids))
    return and_(column.is_(False), User.id.notin_(admin_ids))


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

    # BOT_ADMINS всегда отображаются как trusted/moderator (см. цикл ниже), поэтому
    # фильтр должен учитывать их прямо в SQL -- иначе is_trusted=false вернёт админа,
    # который в выдаче помечен Trusted.
    admin_ids = settings.BOT_ADMINS

    if is_trusted is not None:
        stmt = stmt.where(_flag_filter(User.is_trusted, is_trusted, admin_ids))

    if is_bot_moderator is not None:
        stmt = stmt.where(_flag_filter(User.is_bot_moderator, is_bot_moderator, admin_ids))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(count_stmt) or 0

    if sort_by == "badges":
        sort_column = (
            case((User.is_bot_moderator.is_(True), 10), else_=0)
            + case((User.is_trusted.is_(True), 5), else_=0)
            + case((User.is_premium.is_(True), 1), else_=0)
        )
    else:
        sort_column = getattr(User, sort_by, User.created_at)

    # User.id.desc() -- tie-breaker: без него строки с равным sort_column (например,
    # одинаковым весом бейджей) отдаются в неопределённом порядке, пагинация дублирует/
    # пропускает записи. nullslast() -- юзеры без username не должны быть первыми при desc.
    if sort_order == "asc":
        stmt = stmt.order_by(sort_column.asc().nullslast(), User.id.desc())
    else:
        stmt = stmt.order_by(sort_column.desc().nullslast(), User.id.desc())

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

    # UserChat.chat_id.desc() -- tie-breaker: у UserChat составной PK (user_id, chat_id),
    # без него строки с равным updated_at отдаются в неопределённом порядке.
    stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(UserChat.updated_at.desc(), UserChat.chat_id.desc())
    result = await session.execute(stmt)
    user_chats = result.scalars().all()

    return user_chats, total


async def delete_user(session: AsyncSession, user_id: int) -> None:
    """
    Удаляет пользователя и все связанные с ним данные из базы.

    Удаляет: captcha_sessions, warns, trust_history, user_chats.
    Обнуляет: triggers.created_by, moderation_history.actor_id, warns.admin_id.
    """
    # Обнулить created_by у триггеров
    await session.execute(update(Trigger).where(Trigger.created_by == user_id).values(created_by=None))

    # moderation_history.actor_id уже имеет ondelete=SET NULL в FK,
    # но для надёжности обнулим вручную
    await session.execute(update(ModerationHistory).where(ModerationHistory.actor_id == user_id).values(actor_id=None))

    # Обнулить warns.admin_id где пользователь был админом, выдавшим варн
    await session.execute(update(Warn).where(Warn.admin_id == user_id).values(admin_id=None))

    # Удалить записи, где пользователь — субъект
    await session.execute(delete(ChatCaptchaSession).where(ChatCaptchaSession.user_id == user_id))
    await session.execute(delete(Warn).where(Warn.user_id == user_id))
    await session.execute(delete(ChatTrustHistory).where(ChatTrustHistory.user_id == user_id))
    await session.execute(delete(UserChat).where(UserChat.user_id == user_id))

    # Удалить самого пользователя
    await session.execute(delete(User).where(User.id == user_id))

    await session.commit()
    logger.info("User %d and all related data deleted", user_id)
