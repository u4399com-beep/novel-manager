"""add_crawl_sessions_and_system_state

Revision ID: 3a234d243a23
Revises: 5443dc1b2227
Create Date: 2026-06-29 20:23:51.598913

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '3a234d243a23'
down_revision: Union[str, Sequence[str], None] = '5443dc1b2227'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # crawl_sessions — cross-worker SSE session metadata (DB-backed)
    op.create_table(
        'crawl_sessions',
        sa.Column('task_id', sa.String(36), primary_key=True),
        sa.Column('novel_title', sa.String(255), nullable=False, server_default=''),
        sa.Column('status', sa.String(16), nullable=False, server_default='running'),
        sa.Column('worker_pid', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
    )

    # system_state — distributed lock for queue coordination (no Redis needed)
    op.create_table(
        'system_state',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('value', sa.Text, nullable=True),
        sa.Column('worker_pid', sa.Integer, nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lock_ttl', sa.Integer, nullable=False, server_default='60'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
    )


def downgrade() -> None:
    op.drop_table('system_state')
    op.drop_table('crawl_sessions')
