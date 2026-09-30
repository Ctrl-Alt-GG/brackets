"""Remove courts

Matches are no longer queued on courts: every match of a round starts at the same time. The courts
table goes away together with the match columns that placed a match in a court's queue.

Revision ID: 5c1f0e9a7d42
Revises: b7c3d91f2a04
Create Date: 2026-09-30 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "5c1f0e9a7d42"
down_revision: str | None = "b7c3d91f2a04"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Dropping the column also drops its foreign key to courts.
    op.drop_column("matches", "court_id")
    op.drop_column("matches", "position_in_schedule")
    op.drop_table("courts")
    op.drop_column("tournaments", "auto_assign_courts")


def downgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("auto_assign_courts", sa.Boolean(), server_default="f", nullable=False),
    )
    op.create_table(
        "courts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name="courts_tournament_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_courts_id"), "courts", ["id"], unique=False)
    op.create_index(op.f("ix_courts_tournament_id"), "courts", ["tournament_id"], unique=False)
    op.add_column("matches", sa.Column("position_in_schedule", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("court_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "matches_court_id_fkey", "matches", "courts", ["court_id"], ["id"], ondelete="SET NULL"
    )
