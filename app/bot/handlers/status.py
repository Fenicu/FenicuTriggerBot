from aiogram import Router
from aiogram.filters import ADMINISTRATOR, CREATOR, KICKED, LEFT, MEMBER, RESTRICTED, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_service import update_chat_settings

router = Router()


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED | LEFT))
async def on_bot_kicked(event: ChatMemberUpdated, session: AsyncSession) -> None:
    """Бот был удален из чата."""
    await update_chat_settings(session, event.chat.id, is_active=False)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER | ADMINISTRATOR | CREATOR | RESTRICTED))
async def on_bot_added(event: ChatMemberUpdated, session: AsyncSession) -> None:
    """Бот был добавлен в чат или восстановлен."""
    await update_chat_settings(session, event.chat.id, is_active=True)
