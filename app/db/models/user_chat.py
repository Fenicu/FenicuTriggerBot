from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

if TYPE_CHECKING:
    from app.db.models.chat import Chat
    from app.db.models.user import User


class UserChat(Base):
    __tablename__ = "user_chats"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), primary_key=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    captcha_passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reputation_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reputation_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tag_is_manual: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    daily_message_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    daily_message_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="chats")
    chat: Mapped["Chat"] = relationship("Chat", back_populates="users")


async def has_passed_chat_captcha(session: AsyncSession, chat_id: int, user_id: int) -> bool:
    return (
        await session.scalar(
            select(UserChat.captcha_passed_at).where(UserChat.chat_id == chat_id, UserChat.user_id == user_id)
        )
        is not None
    )


async def mark_chat_captcha_passed(session: AsyncSession, chat_id: int, user_id: int) -> None:
    stmt = insert(UserChat).values(user_id=user_id, chat_id=chat_id, captcha_passed_at=func.now())
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[UserChat.user_id, UserChat.chat_id],
            set_={"captcha_passed_at": func.coalesce(UserChat.captcha_passed_at, stmt.excluded.captcha_passed_at)},
        )
    )
