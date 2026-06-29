"""add_translate_enabled_to_sites

Revision ID: 5443dc1b2227
Revises: 0c9a47e623bb
Create Date: 2026-06-29 16:09:57.471901

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '5443dc1b2227'
down_revision: Union[str, Sequence[str], None] = '0c9a47e623bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Columns already created by 354e21e3b916 (full table)."""
    pass


def downgrade() -> None:
    pass
