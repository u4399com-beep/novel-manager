"""add_url_patterns_pagination_link_rings

Revision ID: b7607ea46936
Revises: 354e21e3b916
Create Date: 2026-06-28 11:33:13.301819

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b7607ea46936'
down_revision: Union[str, Sequence[str], None] = '354e21e3b916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # link_ring_targets
    op.create_table('link_ring_targets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('ring_id', sa.String(length=36), nullable=False),
        sa.Column('source_site_id', sa.String(length=36), nullable=True),
        sa.Column('source_novel_id', sa.String(length=36), nullable=True),
        sa.Column('target_site_id', sa.String(length=36), nullable=True),
        sa.Column('target_novel_id', sa.String(length=36), nullable=True),
        sa.Column('target_url', sa.String(length=500), nullable=True),
        sa.Column('anchor_text', sa.String(length=200), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_link_ring_targets_id'), 'link_ring_targets', ['id'], unique=False)
    op.create_index(op.f('ix_link_ring_targets_ring_id'), 'link_ring_targets', ['ring_id'], unique=False)

    # link_rings
    op.create_table('link_rings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('ring_type', sa.String(length=30), nullable=False),
        sa.Column('site_id', sa.String(length=36), nullable=True),
        sa.Column('max_links', sa.Integer(), nullable=False),
        sa.Column('display_mode', sa.String(length=20), nullable=False),
        sa.Column('link_format', sa.String(length=500), nullable=False),
        sa.Column('open_new_tab', sa.Boolean(), nullable=False),
        sa.Column('nofollow', sa.Boolean(), nullable=False),
        sa.Column('selection_rules', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_link_rings_id'), 'link_rings', ['id'], unique=False)
    op.create_index(op.f('ix_link_rings_site_id'), 'link_rings', ['site_id'], unique=False)

    # Sites columns already in 354e21e3b916 — skip ALTER TABLE


def downgrade() -> None:
    op.drop_index(op.f('ix_link_rings_site_id'), table_name='link_rings')
    op.drop_index(op.f('ix_link_rings_id'), table_name='link_rings')
    op.drop_table('link_rings')
    op.drop_index(op.f('ix_link_ring_targets_ring_id'), table_name='link_ring_targets')
    op.drop_index(op.f('ix_link_ring_targets_id'), table_name='link_ring_targets')
    op.drop_table('link_ring_targets')
