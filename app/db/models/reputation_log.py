from datetime import date as date_type

from sqlalchemy import BigInteger, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ReputationLog(Base):
    """Лог репутационных действий за день (антифлуд)."""

    __tablename__ = "reputation_logs"
    __table_args__ = (
        UniqueConstraint("chat_id", "from_user_id", "to_user_id", "action_type", "date", name="uq_reputation_log"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    to_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "reaction" | "reply"
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
