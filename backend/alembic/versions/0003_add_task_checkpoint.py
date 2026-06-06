"""add task checkpoint

Revision ID: 0003_add_task_checkpoint
Revises: 0002_add_task_mode
Create Date: 2026-06-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_task_checkpoint"
down_revision: str | None = "0002_add_task_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "checkpoint",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "checkpoint")
