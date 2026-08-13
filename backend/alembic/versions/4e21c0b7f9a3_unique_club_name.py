"""unique club name

Revision ID: 4e21c0b7f9a3
Revises: 9f8f4b6d2b31
Create Date: 2026-08-13 10:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "4e21c0b7f9a3"
down_revision: str | None = "9f8f4b6d2b31"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Existing rows may hold duplicates; keep the oldest name and suffix the rest with their id.
    op.execute(
        """
        UPDATE clubs
        SET name = clubs.name || ' (' || clubs.id || ')'
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY name ORDER BY id) AS row_number
            FROM clubs
        ) AS duplicates
        WHERE clubs.id = duplicates.id AND duplicates.row_number > 1
        """
    )
    op.drop_index("ix_clubs_name", table_name="clubs")
    op.create_index(op.f("ix_clubs_name"), "clubs", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_clubs_name"), table_name="clubs")
    op.create_index("ix_clubs_name", "clubs", ["name"], unique=False)
