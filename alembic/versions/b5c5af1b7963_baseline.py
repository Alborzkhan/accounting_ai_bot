"""baseline — empty on purpose; accounting.db already matches current models
via the manual ALTER-TABLE shim in database/models.py. Real schema changes
start from the next revision.

Revision ID: b5c5af1b7963
Revises:
Create Date: 2026-06-22 15:05:20.848163
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5c5af1b7963'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
