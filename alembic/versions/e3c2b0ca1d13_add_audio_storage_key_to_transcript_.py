"""add audio_storage_key to transcript_turns

Revision ID: e3c2b0ca1d13
Revises: a29a4d123d0e
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e3c2b0ca1d13'
down_revision: Union[str, Sequence[str], None] = 'a29a4d123d0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('transcript_turns', sa.Column('audio_storage_key', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('transcript_turns', 'audio_storage_key')
