"""Details links in lowercase, one ranking per position

- `tournaments.dashboard_endpoint`, the Details link, is stored in lowercase, and unique and looked
  up regardless of case. `Cup` and `cup` could both exist, and a player who typed the link with
  other capitals got an error.
- The rankings of a tournament are numbered 0, 1, 2, ... in the order they had. Two rankings could
  share a position, which left open which of them is the default.

Revision ID: b2e5c8d1f4a7
Revises: a1d4e7c9b2f3
Create Date: 2026-11-14 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b2e5c8d1f4a7"
down_revision: str | None = "a1d4e7c9b2f3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    colliding_links = (
        op.get_bind()
        .exec_driver_sql(
            """
            SELECT lower(dashboard_endpoint), string_agg(id::text, ', ' ORDER BY id)
            FROM tournaments
            WHERE dashboard_endpoint IS NOT NULL
            GROUP BY lower(dashboard_endpoint)
            HAVING count(*) > 1
            """
        )
        .fetchall()
    )
    if colliding_links:
        collisions = "; ".join(
            f'"{link}" (tournaments {tournament_ids})' for link, tournament_ids in colliding_links
        )
        raise RuntimeError(
            "Details links can't be made lowercase, because these differ only by case: "
            f"{collisions}. Give all but one of each another Details link, in the tournament "
            "settings of the previous version or in the database, then upgrade again."
        )

    op.execute(
        """
        UPDATE tournaments
        SET dashboard_endpoint = lower(dashboard_endpoint)
        WHERE dashboard_endpoint <> lower(dashboard_endpoint)
        """
    )
    op.drop_index("ix_tournaments_dashboard_endpoint", table_name="tournaments")
    op.execute(
        "CREATE UNIQUE INDEX ix_tournaments_dashboard_endpoint_lower "
        "ON tournaments (lower(dashboard_endpoint))"
    )

    op.execute(
        """
        UPDATE rankings
        SET position = numbered.new_position
        FROM (
            SELECT
                id,
                ROW_NUMBER() OVER (PARTITION BY tournament_id ORDER BY position, id) - 1
                    AS new_position
            FROM rankings
        ) AS numbered
        WHERE rankings.id = numbered.id AND rankings.position <> numbered.new_position
        """
    )


def downgrade() -> None:
    op.drop_index("ix_tournaments_dashboard_endpoint_lower", table_name="tournaments")
    op.create_index(
        "ix_tournaments_dashboard_endpoint", "tournaments", ["dashboard_endpoint"], unique=True
    )
