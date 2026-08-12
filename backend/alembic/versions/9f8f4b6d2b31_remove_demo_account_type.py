"""Remove demo account type

Revision ID: 9f8f4b6d2b31
Revises: 6d5f2a8ec1b1
Create Date: 2026-08-12 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "9f8f4b6d2b31"
down_revision: str | None = "6d5f2a8ec1b1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET account_type = 'REGULAR' WHERE account_type = 'DEMO';")
    op.execute("ALTER TYPE account_type RENAME TO account_type_old;")
    op.execute("CREATE TYPE account_type AS ENUM ('REGULAR');")
    op.execute(
        "ALTER TABLE users ALTER COLUMN account_type TYPE account_type "
        "USING account_type::text::account_type;"
    )
    op.execute("DROP TYPE account_type_old;")


def downgrade() -> None:
    op.execute("ALTER TYPE account_type RENAME TO account_type_old;")
    op.execute("CREATE TYPE account_type AS ENUM ('REGULAR', 'DEMO');")
    op.execute(
        "ALTER TABLE users ALTER COLUMN account_type TYPE account_type "
        "USING account_type::text::account_type;"
    )
    op.execute("DROP TYPE account_type_old;")
