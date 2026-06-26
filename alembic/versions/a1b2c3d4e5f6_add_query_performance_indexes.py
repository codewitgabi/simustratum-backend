"""add query performance indexes

Revision ID: a1b2c3d4e5f6
Revises: c8d7e6f5a4b3
Create Date: 2026-06-26 12:00:00.000000

Two composite indexes that match the two most frequent read queries:

  list_sessions: WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3
  get_session_replay turns: WHERE session_id = $1 ORDER BY sequence

Without these, Aurora must perform an index scan on the single-column FK index
then a separate sort step. The composite indexes allow Aurora's query planner to
satisfy both the filter and the ORDER BY from a single index scan — no sort node
in the execution plan.

The NULLS FIRST on expires_at keeps Aurora from placing NULL token rows at the
top of any range scan when the cleanup query runs.

Note: CREATE INDEX CONCURRENTLY cannot run inside a transaction block. These are
plain non-concurrent builds which take a brief exclusive lock — acceptable during
the CI deploy window when zero user traffic hits the database.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c8d7e6f5a4b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Covers: SELECT ... FROM sessions WHERE user_id = $1 ORDER BY created_at DESC
    # The DESC matches the order() clause in list_sessions exactly — Aurora can
    # walk the index in reverse without an extra sort node.
    op.create_index(
        "idx_sessions_user_created",
        "sessions",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )

    # Covers: SELECT ... FROM transcript_turns WHERE session_id = $1 ORDER BY sequence
    # A composite index on (session_id, sequence) lets Aurora fetch the turns for
    # a session replay already in order — no filesort needed even for long sessions.
    op.create_index(
        "idx_transcript_turns_session_seq",
        "transcript_turns",
        ["session_id", "sequence"],
        unique=False,
    )

    # Supports future periodic cleanup of expired blacklisted tokens.
    # DELETE FROM token_blacklist WHERE expires_at < NOW() would otherwise scan
    # the whole table; this bounds it to only expired rows.
    op.create_index(
        "idx_token_blacklist_expires",
        "token_blacklist",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_token_blacklist_expires", table_name="token_blacklist")
    op.drop_index("idx_transcript_turns_session_seq", table_name="transcript_turns")
    op.drop_index("idx_sessions_user_created", table_name="sessions")
