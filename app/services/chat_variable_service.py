import re

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat_variable import ChatVariable


async def set_var(session: AsyncSession, chat_id: int, key: str, value: str) -> None:
    """Установить переменную чата."""
    stmt = (
        insert(ChatVariable)
        .values(chat_id=chat_id, key=key, value=value)
        .on_conflict_do_update(
            index_elements=[ChatVariable.chat_id, ChatVariable.key],
            set_={"value": value},
        )
    )
    await session.execute(stmt)
    await session.commit()


async def del_var(session: AsyncSession, chat_id: int, key: str) -> bool:
    """Удалить переменную чата."""
    stmt = delete(ChatVariable).where(ChatVariable.chat_id == chat_id, ChatVariable.key == key)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def get_vars(session: AsyncSession, chat_id: int) -> dict[str, str]:
    """Получить все переменные чата."""
    stmt = select(ChatVariable).where(ChatVariable.chat_id == chat_id)
    result = await session.execute(stmt)
    variables = result.scalars().all()
    return {var.key: var.value for var in variables}


def validate_key(key: str) -> bool:
    """Валидировать ключ переменной: только латиница и _."""
    return bool(re.match(r"^[a-zA-Z_]+$", key))
