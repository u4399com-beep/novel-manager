"""add_recommend_modules

Revision ID: fe169271913a
Revises: b7607ea46936
Create Date: 2026-06-28 11:58:27.735253

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'fe169271913a'
down_revision: Union[str, Sequence[str], None] = 'b7607ea46936'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Columns already created by 354e21e3b916 (full table)."""
    pass


def downgrade() -> None:
    pass
