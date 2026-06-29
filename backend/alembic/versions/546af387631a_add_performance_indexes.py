"""add_performance_indexes

Revision ID: 546af387631a
Revises: 7455ca9b9b90
Create Date: 2026-06-28 22:50:17.322766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


revision: str = '546af387631a'
down_revision: Union[str, Sequence[str], None] = '7455ca9b9b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _safe_create_index(name: str, table: str, cols: list[str], unique: bool = False):
    """Idempotent index creation — catches Duplicate key name (err 1061)."""
    try:
        op.create_index(name, table, cols, unique=unique)
    except OperationalError as e:
        if hasattr(e.orig, 'args') and e.orig.args and '1061' in str(e.orig.args[0]):
            pass  # already exists from partial prior run
        else:
            raise


def _safe_drop_index(name: str, table: str):
    """Idempotent index drop — DROP INDEX IF EXISTS (PostgreSQL + MySQL compatible)."""
    op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))


def upgrade() -> None:
    """Add 8 performance composite indexes; drop redundant duplicate-PK indexes."""
    # --- Data cleanup: NULL out junk source_url values ---
    op.execute(sa.text(
        "UPDATE chapters SET source_url = NULL WHERE source_url LIKE 'javascript:%'"
    ))

    # P0: chapters(novel_id, sort_order) — every page: chapter lists, prev/next, dedup
    _safe_create_index('ix_chapters_novel_sort', 'chapters', ['novel_id', 'sort_order'], unique=False)
    # P1: chapters(novel_id, source_url) — crawler incremental dedup (non-unique due to legacy dupes)
    _safe_create_index('ix_chapters_novel_source_url', 'chapters', ['novel_id', 'source_url'], unique=False)
    # P2: chapters(novel_id, is_published) — stats COUNT WHERE
    _safe_create_index('ix_chapters_novel_published', 'chapters', ['novel_id', 'is_published'], unique=False)

    # P0: crawler_tasks(status, created_at) — queue worker poll loop
    _safe_create_index('ix_crawler_tasks_status_created', 'crawler_tasks', ['status', 'created_at'], unique=False)
    # P2: crawler_tasks(novel_id, status) — task listing by novel+status
    _safe_create_index('ix_crawler_tasks_novel_status', 'crawler_tasks', ['novel_id', 'status'], unique=False)

    # P1: novels(status, updated_at) — list_novels filter+sort
    _safe_create_index('ix_novels_status_updated', 'novels', ['status', 'updated_at'], unique=False)
    # P1: novels(source_url) UNIQUE — queue range dedup + import dedup guard
    _safe_create_index('ix_novels_source_url', 'novels', ['source_url'], unique=True)

    # P2: link_rings(is_active, site_id) — every page render (link wheel)
    _safe_create_index('ix_link_rings_active_site', 'link_rings', ['is_active', 'site_id'], unique=False)

    # Remove redundant duplicate-PK secondary indexes
    for t in ['chapters', 'crawler_tasks', 'link_ring_targets', 'link_rings',
              'novels', 'sites', 'users', 'translation_cache']:
        _safe_drop_index(f'ix_{t}_id', t)

    # Remove redundant: covered by leading column of ix_translation_lookup (source_hash, target_lang)
    _safe_drop_index('ix_translation_cache_source_hash', 'translation_cache')
    _safe_drop_index('ix_translation_cache_target_lang', 'translation_cache')


def downgrade() -> None:
    """Remove new composite indexes; restore redundant PK indexes."""
    op.create_index('ix_translation_cache_target_lang', 'translation_cache', ['target_lang'], unique=False)
    op.create_index('ix_translation_cache_source_hash', 'translation_cache', ['source_hash'], unique=False)
    for t in ['translation_cache', 'users', 'sites', 'novels', 'link_rings',
              'link_ring_targets', 'crawler_tasks', 'chapters']:
        op.create_index(f'ix_{t}_id', t, ['id'], unique=False)

    op.execute(sa.text("DROP INDEX IF EXISTS ix_link_rings_active_site"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_novels_source_url"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_novels_status_updated"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_crawler_tasks_novel_status"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_crawler_tasks_status_created"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chapters_novel_published"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chapters_novel_source_url"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chapters_novel_sort"))
