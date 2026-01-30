from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class ModerationStep(StrEnum):
    """Этапы модерации триггера."""

    CREATED = "created"
    QUEUED = "queued"

    PROCESSING_STARTED = "processing_started"
    MEDIA_PROCESSING = "media_processing"
    MEDIA_PROCESSED = "media_processed"
    VISION_ANALYZING = "vision_analyzing"
    VISION_COMPLETED = "vision_completed"
    TEXT_ANALYZING = "text_analyzing"
    TEXT_COMPLETED = "text_completed"

    AUTO_APPROVED = "auto_approved"
    AUTO_FLAGGED = "auto_flagged"
    AUTO_ERROR = "auto_error"

    ALERT_SENT = "alert_sent"
    MANUAL_APPROVED = "manual_approved"
    MANUAL_DELETED = "manual_deleted"
    MANUAL_BANNED = "manual_banned"
    REQUEUED = "requeued"


class ModerationHistory(Base):
    """История модерации триггера."""

    __tablename__ = "moderation_history"
    __table_args__ = (
        Index("ix_moderation_history_trigger_id", "trigger_id"),
        Index("ix_moderation_history_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("triggers.id", ondelete="CASCADE"),
        nullable=False,
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    trigger = relationship("Trigger", back_populates="moderation_history")
