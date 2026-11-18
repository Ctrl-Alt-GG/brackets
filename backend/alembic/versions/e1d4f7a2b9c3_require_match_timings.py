"""Require every match to have a duration and a margin.

The planner gives every match both, but matches of older versions can lack them. Those get the
values the planner would give them: the match's own, otherwise the stage's custom duration and the
tournament's defaults.

Revision ID: e1d4f7a2b9c3
Revises: c3f6a9d2e5b8
Create Date: 2026-11-17 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "e1d4f7a2b9c3"
down_revision: str = "c3f6a9d2e5b8"
branch_labels: str | None = None
depends_on: str | None = None


def _replace_checks(*, nullable: bool) -> None:
    allow_null = "{column} IS NULL OR " if nullable else ""
    for name, column, minimum in (
        ("ck_matches_duration", "duration_minutes", 1),
        ("ck_matches_margin", "margin_minutes", 0),
    ):
        op.drop_constraint(name, "matches", type_="check")
        op.alter_column("matches", column, nullable=nullable, existing_type=sa.Integer())
        op.create_check_constraint(
            name,
            "matches",
            f"{allow_null.format(column=column)}{column} BETWEEN {minimum} AND 1440",
        )


def upgrade() -> None:
    op.execute(
        "UPDATE matches m SET "
        "duration_minutes = COALESCE("
        "m.duration_minutes, m.custom_duration_minutes, s.custom_duration_minutes, "
        "t.duration_minutes), "
        "margin_minutes = COALESCE(m.margin_minutes, m.custom_margin_minutes, t.margin_minutes) "
        "FROM rounds r "
        "JOIN stage_items si ON si.id = r.stage_item_id "
        "JOIN stages s ON s.id = si.stage_id "
        "JOIN tournaments t ON t.id = s.tournament_id "
        "WHERE r.id = m.round_id AND (m.duration_minutes IS NULL OR m.margin_minutes IS NULL)"
    )
    _replace_checks(nullable=False)


def downgrade() -> None:
    _replace_checks(nullable=True)
