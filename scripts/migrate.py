"""
Run Alembic migrations.

Usage:
    python scripts/migrate.py              # upgrades to head
    python scripts/migrate.py downgrade -1 # downgrades one step
    python scripts/migrate.py current      # any standard Alembic command works

The actual database URL — an IAM-authenticated Aurora connection when DB_HOST
is set, or the plain DATABASE_URL from .env otherwise — is resolved by
alembic/env.py itself, exactly as it is when running `alembic` directly. This
script is just a friendlier entrypoint that doesn't require the alembic CLI
to be on PATH.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from alembic import command
from alembic.config import Config as AlembicConfig


def main() -> None:
    args = sys.argv[1:] if len(sys.argv) > 1 else ["upgrade", "head"]
    command_name, *command_args = args

    if not hasattr(command, command_name):
        print(f"Unknown alembic command: {command_name}", file=sys.stderr)
        sys.exit(1)

    alembic_cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))

    getattr(command, command_name)(alembic_cfg, *command_args)


if __name__ == "__main__":
    main()
