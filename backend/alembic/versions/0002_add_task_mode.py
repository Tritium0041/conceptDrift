"""add task mode

Revision ID: 0002_add_task_mode
Revises: 0001_initial
Create Date: 2026-06-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_task_mode"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "mode",
            sa.String(length=20),
            nullable=False,
            server_default="guided",
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "mode")
