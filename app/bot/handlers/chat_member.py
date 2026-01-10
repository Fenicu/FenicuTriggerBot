import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_chat import UserChat
from app.services.chat_service import get_or_create_chat
from app.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)

router = Router()


@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated, session: AsyncSession) -> None:
    """Обработчик изменений статуса участника чата."""
    user = event.new_chat_member.user
    chat = event.chat

    if chat.type == "private":
        return

    await get_or_create_user(
        session=session,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_premium=user.is_premium,
    )

    photo_id = None
    if chat.photo:
        photo_id = chat.photo.big_file_id

    await get_or_create_chat(
        session=session,
        chat_id=chat.id,
        title=chat.title,
        username=chat.username,
        type=chat.type,
        description=chat.description,
        invite_link=chat.invite_link,
        photo_id=photo_id,
    )

    new_status = event.new_chat_member.status

    is_active = new_status in ("member", "administrator", "creator", "restricted")
    is_admin = new_status in ("administrator", "creator")

    user_chat = await session.get(UserChat, (user.id, chat.id))
    if not user_chat:
        user_chat = UserChat(
            user_id=user.id,
            chat_id=chat.id,
            is_active=is_active,
            is_admin=is_admin,
        )
        session.add(user_chat)
    else:
        user_chat.is_active = is_active
        user_chat.is_admin = is_admin
        user_chat.updated_at = datetime.now().astimezone()

    await session.commit()
    logger.info(f"Updated UserChat {user.id} in {chat.id}: active={is_active}, admin={is_admin}")
