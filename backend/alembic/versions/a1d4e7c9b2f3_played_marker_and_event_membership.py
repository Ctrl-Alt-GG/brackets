"""Played marker for matches, event names per organizer, one membership per user, logout

- `matches.scoreless_result` marks a match that ended 0-0. Until now 0-0 could only mean "not
  played yet".
- Event (club) names were unique across the whole site, which told one organizer what another
  had named theirs. The route now keeps them unique per organizer.
- A user is a member of an event once, now that events can have more than one organizer.
- `revoked_sessions` holds the sessions that were ended by logging out, so that a copied token
  stops working too.

Revision ID: a1d4e7c9b2f3
Revises: 4bd9ed491c68
Create Date: 2026-11-11 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "a1d4e7c9b2f3"
down_revision: str | None = "4bd9ed491c68"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("scoreless_result", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.drop_index("ix_clubs_name", table_name="clubs")
    op.create_index(op.f("ix_clubs_name"), "clubs", ["name"], unique=False)

    # Keep one membership of a user in an event, should there be more than one: the one that
    # makes them its owner, otherwise the oldest.
    op.execute(
        """
        DELETE FROM users_x_clubs
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY club_id, user_id
                        ORDER BY (relation = 'OWNER') DESC, id
                    ) AS row_number
                FROM users_x_clubs
            ) AS ranked
            WHERE ranked.row_number > 1
        )
        """
    )
    op.create_unique_constraint(
        "users_x_clubs_club_id_user_id_key", "users_x_clubs", ["club_id", "user_id"]
    )

    op.create_table(
        "revoked_sessions",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(op.f("ix_revoked_sessions_expires"), "revoked_sessions", ["expires"])


def downgrade() -> None:
    op.drop_index(op.f("ix_revoked_sessions_expires"), table_name="revoked_sessions")
    op.drop_table("revoked_sessions")

    op.drop_constraint("users_x_clubs_club_id_user_id_key", "users_x_clubs", type_="unique")

    # Names that became duplicates in the meantime get their id appended, as in `4e21c0b7f9a3`.
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
    op.drop_index(op.f("ix_clubs_name"), table_name="clubs")
    op.create_index("ix_clubs_name", "clubs", ["name"], unique=True)

    op.drop_column("matches", "scoreless_result")
