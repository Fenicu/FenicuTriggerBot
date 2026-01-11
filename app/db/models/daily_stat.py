from datetime import date as date_type

from sqlalchemy import Date, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DailyStat(Base):
    """Модель для хранения ежедневной статистики."""

    __tablename__ = "daily_stats"

    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    messages_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    triggers_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
