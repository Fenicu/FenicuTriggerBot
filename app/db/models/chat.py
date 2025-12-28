from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Chat(Base):
    """Модель чата."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    admins_only_add: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    language_code: Mapped[str] = mapped_column(String(10), default="ru", server_default="ru", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, admins_only_add={self.admins_only_add})>"


class BannedChat(Base):
    """Забаненный чат."""

    __tablename__ = "banned_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    banned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<BannedChat(chat_id={self.chat_id}, reason='{self.reason}')>"
