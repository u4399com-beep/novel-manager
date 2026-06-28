"""add_fulltext_search_index

Revision ID: 0c9a47e623bb
Revises: 546af387631a
Create Date: 2026-06-28 23:38:16.828919

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0c9a47e623bb'
down_revision: Union[str, Sequence[str], None] = '546af387631a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add FULLTEXT index on chapters(title) with ngram parser for Chinese text."""
    op.execute(sa.text(
        "CREATE FULLTEXT INDEX ft_chapters_search ON chapters (title) WITH PARSER ngram"
    ))


def downgrade() -> None:
    """Remove the FULLTEXT index."""
    op.execute(sa.text(
        "DROP INDEX ft_chapters_search ON chapters"
    ))
