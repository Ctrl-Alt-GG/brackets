"""Add stages custom_duration_minutes

A stage can overwrite the tournament's match duration for its own matches.

Revision ID: 4bd9ed491c68
Revises: 5c1f0e9a7d42
Create Date: 2026-09-30 15:13:05.185720

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "4bd9ed491c68"
down_revision: str | None = "5c1f0e9a7d42"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("stages", sa.Column("custom_duration_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("stages", "custom_duration_minutes")
