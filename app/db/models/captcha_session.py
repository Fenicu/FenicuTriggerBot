import secrets
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    update,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class CaptchaSessionKind(StrEnum):
    """Тип сессии капчи: обычный чат или заявка на вступление."""

    CHAT = "chat"
    JOIN_REQUEST = "join_request"


class CaptchaSessionStatus(StrEnum):
    """Состояние сессии капчи (state machine)."""

    PENDING = "pending"
    PASSED = "passed"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"


class ChatCaptchaSession(Base):
    """Сессия капчи для пользователя в чате."""

    __tablename__ = "chat_captcha_sessions"
    __table_args__ = (
        UniqueConstraint("token", name="uq_captcha_token"),
        UniqueConstraint("join_request_query_id", name="uq_captcha_join_request_query_id"),
        CheckConstraint(
            "kind != 'join_request' OR join_request_query_id IS NOT NULL",
            name="ck_captcha_join_request_has_query",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ephemeral_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    kind: Mapped[CaptchaSessionKind] = mapped_column(
        PgEnum(
            CaptchaSessionKind,
            name="captcha_session_kind",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=CaptchaSessionKind.CHAT,
        server_default=CaptchaSessionKind.CHAT.value,
    )
    status: Mapped[CaptchaSessionStatus] = mapped_column(
        PgEnum(
            CaptchaSessionStatus,
            name="captcha_session_status",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=CaptchaSessionStatus.PENDING,
        server_default=CaptchaSessionStatus.PENDING.value,
    )
    join_request_query_id: Mapped[str | None] = mapped_column(String, nullable=True)
    token: Mapped[str] = mapped_column(String, nullable=False, default=lambda: secrets.token_urlsafe(32))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ChatCaptchaSession(id={self.id}, chat_id={self.chat_id}, user_id={self.user_id}, status={self.status})>"
        )


async def claim_session(session: AsyncSession, session_id: int, new_status: CaptchaSessionStatus) -> bool:
    """
    Атомарно переводит сессию капчи из PENDING в new_status.

    Возвращает True, только если именно этот вызов выиграл гонку за переход
    (rowcount == 1). Проигранный claim не должен приводить ни к каким side effect'ам.
    """
    result = await session.execute(
        update(ChatCaptchaSession)
        .where(
            ChatCaptchaSession.id == session_id,
            ChatCaptchaSession.status == CaptchaSessionStatus.PENDING,
        )
        .values(status=new_status)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return result.rowcount == 1
