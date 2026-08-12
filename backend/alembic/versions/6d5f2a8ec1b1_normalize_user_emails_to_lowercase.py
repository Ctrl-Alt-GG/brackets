"""Normalize user emails to lowercase

Revision ID: 6d5f2a8ec1b1
Revises: c1ab44651e79
Create Date: 2026-08-12 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "6d5f2a8ec1b1"
down_revision: str | None = "c1ab44651e79"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    duplicate_rows = (
        op.get_bind()
        .exec_driver_sql(
            """
        SELECT LOWER(email) AS normalized_email
        FROM users
        GROUP BY LOWER(email)
        HAVING COUNT(*) > 1
        """
        )
        .fetchall()
    )
    if duplicate_rows:
        duplicates = ", ".join(row[0] for row in duplicate_rows)
        raise RuntimeError(
            "Cannot normalize user emails because duplicate case-insensitive addresses exist: "
            f"{duplicates}"
        )

    op.execute("UPDATE users SET email = LOWER(email) WHERE email <> LOWER(email);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower ON users (LOWER(email));")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower;")
