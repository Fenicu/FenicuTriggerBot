"""Привяжи прохождение капчи к чату."""

import sqlalchemy as sa
from alembic import op

revision = "c42b8e517d90"
down_revision = "718722086b5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_chats", sa.Column("captcha_passed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("""
        INSERT INTO user_chats (user_id, chat_id, captcha_passed_at)
        SELECT user_id, chat_id, min(created_at)
        FROM chat_captcha_sessions
        WHERE status IN ('passed', 'approved')
        GROUP BY user_id, chat_id
        ON CONFLICT (user_id, chat_id) DO UPDATE
        SET captcha_passed_at = EXCLUDED.captcha_passed_at
    """)


def downgrade() -> None:
    op.drop_column("user_chats", "captcha_passed_at")
