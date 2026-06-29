"""add_language_to_sites

Revision ID: d270add2c830
Revises: fe169271913a
Create Date: 2026-06-28 12:53:07.415763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd270add2c830'
down_revision: Union[str, Sequence[str], None] = 'fe169271913a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Columns already created by 354e21e3b916 (full table)."""
    pass


def downgrade() -> None:
    pass
