from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

if TYPE_CHECKING:
    from app.db.models.user_chat import UserChat


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_premium: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String, nullable=True)

    is_bot_moderator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    chats: Mapped[list["UserChat"]] = relationship("UserChat", back_populates="user")

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
