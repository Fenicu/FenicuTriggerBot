from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.warn import Warn
from app.services.chat_service import update_chat_settings as _update_chat_settings


class ModerationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_warn(self, chat_id: int, user_id: int, admin_id: int, reason: str | None) -> Warn:
        """Добавить предупреждение пользователю."""
        warn = Warn(chat_id=chat_id, user_id=user_id, admin_id=admin_id, reason=reason)
        self.session.add(warn)
        await self.session.commit()
        await self.session.refresh(warn)
        return warn

    async def get_user_warns(self, chat_id: int, user_id: int) -> list[Warn]:
        """Получить список активных предупреждений пользователя."""
        stmt = select(Warn).where(Warn.chat_id == chat_id, Warn.user_id == user_id).order_by(Warn.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_warn_count(self, chat_id: int, user_id: int) -> int:
        """Получить количество предупреждений пользователя."""
        stmt = select(func.count()).select_from(Warn).where(Warn.chat_id == chat_id, Warn.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def remove_last_warn(self, chat_id: int, user_id: int) -> bool:
        """Удалить последнее предупреждение пользователя. Возвращает True, если предупреждение было удалено."""
        stmt = (
            select(Warn)
            .where(Warn.chat_id == chat_id, Warn.user_id == user_id)
            .order_by(desc(Warn.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        warn = result.scalar_one_or_none()

        if warn:
            await self.session.delete(warn)
            await self.session.commit()
            return True
        return False

    async def reset_warns(self, chat_id: int, user_id: int) -> None:
        """Сбросить все предупреждения пользователя в чате."""
        stmt = delete(Warn).where(Warn.chat_id == chat_id, Warn.user_id == user_id)
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_chat_settings(self, chat_id: int, **kwargs) -> Chat:
        """Обновить настройки модерации чата."""
        return await _update_chat_settings(self.session, chat_id, **kwargs)

    async def get_chat_settings(self, chat_id: int) -> Chat:
        """Получить настройки чата."""
        chat = await self.session.get(Chat, chat_id)
        if not chat:
            return Chat(id=chat_id)
        return chat
