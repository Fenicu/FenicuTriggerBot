from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class Warn(Base):
    """Модель предупреждения."""

    __tablename__ = "warns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chat = relationship("Chat", backref="warns")

    __table_args__ = (Index("ix_warns_chat_id_user_id", "chat_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<Warn(id={self.id}, chat_id={self.chat_id}, user_id={self.user_id})>"
