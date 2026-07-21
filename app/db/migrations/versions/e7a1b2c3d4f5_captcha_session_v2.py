"""captcha_session_v2

Revision ID: e7a1b2c3d4f5
Revises: d1e2f3a4b5c6
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a1b2c3d4f5'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "chat_captcha_sessions"

kind_enum = sa.Enum("chat", "join_request", name="captcha_session_kind")
status_enum = sa.Enum("pending", "passed", "approved", "declined", "expired", name="captcha_session_status")


def upgrade() -> None:
    bind = op.get_bind()
    kind_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)

    op.add_column(TABLE, sa.Column("ephemeral_message_id", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("kind", kind_enum, nullable=False, server_default="chat"))
    op.add_column(TABLE, sa.Column("status", status_enum, nullable=False, server_default="pending"))
    op.add_column(TABLE, sa.Column("join_request_query_id", sa.String(), nullable=True))
    op.add_column(TABLE, sa.Column("token", sa.String(), nullable=True))

    op.execute(f"UPDATE {TABLE} SET status = 'passed' WHERE is_completed = true")
    op.execute(f"UPDATE {TABLE} SET token = gen_random_uuid()::text WHERE token IS NULL")

    op.alter_column(TABLE, "token", existing_type=sa.String(), nullable=False)
    op.alter_column(TABLE, "message_id", existing_type=sa.Integer(), nullable=True)
    op.drop_column(TABLE, "is_completed")

    op.create_unique_constraint("uq_captcha_token", TABLE, ["token"])
    op.create_unique_constraint("uq_captcha_join_request_query_id", TABLE, ["join_request_query_id"])
    op.create_check_constraint(
        "ck_captcha_join_request_has_query",
        TABLE,
        "kind != 'join_request' OR join_request_query_id IS NOT NULL",
    )


def downgrade() -> None:
    op.add_column(TABLE, sa.Column("is_completed", sa.Boolean(), server_default="false", nullable=False))
    op.execute(f"UPDATE {TABLE} SET is_completed = true WHERE status IN ('passed', 'approved')")
    op.execute(f"DELETE FROM {TABLE} WHERE kind = 'join_request' OR message_id IS NULL")
    op.drop_constraint("ck_captcha_join_request_has_query", TABLE)
    op.drop_constraint("uq_captcha_token", TABLE)
    op.drop_constraint("uq_captcha_join_request_query_id", TABLE)
    op.drop_column(TABLE, "token")
    op.drop_column(TABLE, "join_request_query_id")
    op.drop_column(TABLE, "status")
    op.drop_column(TABLE, "kind")
    op.drop_column(TABLE, "ephemeral_message_id")
    op.alter_column(TABLE, "message_id", existing_type=sa.Integer(), nullable=False)
    status_enum.drop(op.get_bind(), checkfirst=True)
    kind_enum.drop(op.get_bind(), checkfirst=True)
