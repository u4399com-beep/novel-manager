"""add_sites_table

Revision ID: 354e21e3b916
Revises: 1b02f66a95bc
Create Date: 2026-06-28 10:22:43.239734

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '354e21e3b916'
down_revision: Union[str, Sequence[str], None] = '1b02f66a95bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_unique_title"))

    op.create_table(
        'sites',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('domain', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('template', sa.String(50), server_default='default'),
        sa.Column('offset_val', sa.Integer, server_default='0'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('true')),
        sa.Column('language', sa.String(10), server_default='zh'),
        sa.Column('translate_enabled', sa.Boolean, server_default=sa.text('true')),
        sa.Column('url_patterns', sa.JSON, nullable=True),
        sa.Column('chapter_pagination', sa.JSON, nullable=True),
        sa.Column('link_wheel', sa.JSON, nullable=True),
        sa.Column('recommend_modules', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('sites')
    op.create_index('idx_unique_title', 'novels', ['title'], unique=True)
