from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Chat(Base):
    """Модель чата."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    invite_link: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String, nullable=True)

    admins_only_add: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    language_code: Mapped[str] = mapped_column(String(10), default="ru", server_default="ru", nullable=False)
    warn_limit: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    warn_punishment: Mapped[str] = mapped_column(String(10), default="ban", server_default="ban", nullable=False)
    warn_duration: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, title={self.title}, type={self.type})>"


class BannedChat(Base):
    """Забаненный чат."""

    __tablename__ = "banned_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    banned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<BannedChat(chat_id={self.chat_id}, reason='{self.reason}')>"
