from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ChatVariable(Base):
    """Модель переменной чата."""

    __tablename__ = "chat_variables"

    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<ChatVariable(chat_id={self.chat_id}, key='{self.key}', value='{self.value}')>"
