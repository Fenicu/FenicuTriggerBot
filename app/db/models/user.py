from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)

    is_bot_moderator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
