"""Cascade tournament deletion to owned records

Revision ID: b7c3d91f2a04
Revises: 4e21c0b7f9a3
Create Date: 2026-08-13 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "b7c3d91f2a04"
down_revision: str | None = "4e21c0b7f9a3"
branch_labels: str | None = None
depends_on: str | None = None

# (constraint, table, referent table, local columns, ondelete)
FOREIGN_KEYS = [
    ("stages_tournament_id_fkey", "stages", "tournaments", ["tournament_id"], "CASCADE"),
    (
        "stage_item_inputs_tournament_id_fkey",
        "stage_item_inputs",
        "tournaments",
        ["tournament_id"],
        "CASCADE",
    ),
    ("teams_tournament_id_fkey", "teams", "tournaments", ["tournament_id"], "CASCADE"),
    ("players_tournament_id_fkey", "players", "tournaments", ["tournament_id"], "CASCADE"),
    ("courts_tournament_id_fkey", "courts", "tournaments", ["tournament_id"], "CASCADE"),
    ("rankings_tournament_id_fkey", "rankings", "tournaments", ["tournament_id"], "CASCADE"),
    ("stage_items_stage_id_fkey", "stage_items", "stages", ["stage_id"], "CASCADE"),
    ("stage_items_ranking_id_fkey", "stage_items", "rankings", ["ranking_id"], "CASCADE"),
    ("rounds_stage_item_id_fkey", "rounds", "stage_items", ["stage_item_id"], "CASCADE"),
    ("matches_round_id_fkey", "matches", "rounds", ["round_id"], "CASCADE"),
    ("matches_court_id_fkey", "matches", "courts", ["court_id"], "SET NULL"),
    (
        "matches_stage_item_input1_winner_from_match_id_fkey",
        "matches",
        "matches",
        ["stage_item_input1_winner_from_match_id"],
        "SET NULL",
    ),
    (
        "matches_stage_item_input2_winner_from_match_id_fkey",
        "matches",
        "matches",
        ["stage_item_input2_winner_from_match_id"],
        "SET NULL",
    ),
    (
        "stage_item_inputs_winner_from_stage_item_id_fkey",
        "stage_item_inputs",
        "stage_items",
        ["winner_from_stage_item_id"],
        "SET NULL",
    ),
]


def upgrade() -> None:
    for constraint, table, referent, columns, ondelete in FOREIGN_KEYS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, referent, columns, ["id"], ondelete=ondelete)


def downgrade() -> None:
    for constraint, table, referent, columns, _ in reversed(FOREIGN_KEYS):
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, referent, columns, ["id"])
