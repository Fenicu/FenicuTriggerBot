from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class MatchType(StrEnum):
    """Тип совпадения."""

    EXACT = "exact"
    CONTAINS = "contains"
    REGEXP = "regexp"


class AccessLevel(StrEnum):
    """Уровень доступа."""

    ALL = "all"
    ADMINS = "admins"
    OWNER = "owner"


class ModerationStatus(StrEnum):
    """Статус модерации."""

    PENDING = "pending"
    SAFE = "safe"
    FLAGGED = "flagged"
    BANNED = "banned"
    ERROR = "error"


class Trigger(Base):
    """Модель триггера."""

    __tablename__ = "triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), index=True)
    key_phrase: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    match_type: Mapped[MatchType] = mapped_column(
        PgEnum(MatchType, name="match_type_enum", create_type=False),
        nullable=False,
        default=MatchType.EXACT,
    )
    is_case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    access_level: Mapped[AccessLevel] = mapped_column(
        PgEnum(AccessLevel, name="access_level_enum", create_type=False),
        nullable=False,
        default=AccessLevel.ALL,
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)

    moderation_status: Mapped[ModerationStatus] = mapped_column(
        PgEnum(ModerationStatus, name="moderation_status_enum", create_type=False),
        nullable=False,
        default=ModerationStatus.PENDING,
        server_default=ModerationStatus.PENDING,
    )
    moderation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    chat = relationship("app.db.models.chat.Chat", backref="triggers")

    def __repr__(self) -> str:
        return f"<Trigger(id={self.id}, key_phrase='{self.key_phrase}', chat_id={self.chat_id})>"
