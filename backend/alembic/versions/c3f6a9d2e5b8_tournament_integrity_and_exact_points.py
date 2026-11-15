"""Enforce tournament boundaries, exact points, and structural invariants.

Existing data is checked before altering the schema. Point values are rounded to six decimal
places only when the relative difference is within 1e-14, allowing floating-point artifacts
without zeroing small nonzero rules. Other incompatible data requires an explicit correction.

Revision ID: c3f6a9d2e5b8
Revises: b2e5c8d1f4a7
Create Date: 2026-11-15 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "c3f6a9d2e5b8"
down_revision: str = "b2e5c8d1f4a7"
branch_labels: str | None = None
depends_on: str | None = None

CHECKS = {
    "tournaments": [
        ("ck_tournaments_duration", "duration_minutes BETWEEN 1 AND 1440"),
        ("ck_tournaments_margin", "margin_minutes BETWEEN 0 AND 1440"),
    ],
    "stages": [
        (
            "ck_stages_custom_duration",
            "custom_duration_minutes IS NULL OR custom_duration_minutes BETWEEN 1 AND 1440",
        )
    ],
    "stage_items": [
        ("ck_stage_items_team_count", "team_count BETWEEN 2 AND 64"),
        (
            "ck_stage_items_knockout_team_count",
            "type <> 'SINGLE_ELIMINATION' OR team_count IN (2, 4, 8, 16, 32)",
        ),
    ],
    "stage_item_inputs": [
        ("ck_stage_item_inputs_slot", "slot BETWEEN 1 AND 64"),
        (
            "ck_stage_item_inputs_winner_position",
            "winner_position IS NULL OR winner_position BETWEEN 1 AND 64",
        ),
        ("ck_stage_item_inputs_results", "wins >= 0 AND draws >= 0 AND losses >= 0"),
    ],
    "matches": [
        (
            "ck_matches_scores",
            (
                "stage_item_input1_score BETWEEN 0 AND 100000 "
                "AND stage_item_input2_score BETWEEN 0 AND 100000"
            ),
        ),
        (
            "ck_matches_scoreless_result",
            "NOT scoreless_result OR (stage_item_input1_score = 0 AND stage_item_input2_score = 0)",
        ),
        (
            "ck_matches_distinct_inputs",
            (
                "stage_item_input1_id IS NULL OR stage_item_input2_id IS NULL "
                "OR stage_item_input1_id <> stage_item_input2_id"
            ),
        ),
        ("ck_matches_duration", "duration_minutes IS NULL OR duration_minutes BETWEEN 1 AND 1440"),
        ("ck_matches_margin", "margin_minutes IS NULL OR margin_minutes BETWEEN 0 AND 1440"),
        (
            "ck_matches_custom_duration",
            "custom_duration_minutes IS NULL OR custom_duration_minutes BETWEEN 1 AND 1440",
        ),
        (
            "ck_matches_custom_margin",
            "custom_margin_minutes IS NULL OR custom_margin_minutes BETWEEN 0 AND 1440",
        ),
    ],
    "rankings": [
        ("ck_rankings_position", "position >= 0"),
        (
            "ck_rankings_points",
            (
                "win_points BETWEEN -1000 AND 1000 AND draw_points BETWEEN -1000 AND 1000 "
                "AND loss_points BETWEEN -1000 AND 1000"
            ),
        ),
    ],
    "teams": [("ck_teams_results", "wins >= 0 AND draws >= 0 AND losses >= 0")],
    "players": [("ck_players_results", "wins >= 0 AND draws >= 0 AND losses >= 0")],
}

SCOPED_FOREIGN_KEYS = [
    (
        "stage_items_stage_id_fkey",
        "stage_items",
        "stages",
        ["stage_id", "tournament_id"],
        "CASCADE",
    ),
    (
        "stage_items_ranking_id_fkey",
        "stage_items",
        "rankings",
        ["ranking_id", "tournament_id"],
        "CASCADE",
    ),
    (
        "rounds_stage_item_id_fkey",
        "rounds",
        "stage_items",
        ["stage_item_id", "tournament_id"],
        "CASCADE",
    ),
    ("matches_round_id_fkey", "matches", "rounds", ["round_id", "tournament_id"], "CASCADE"),
    (
        "matches_stage_item_input1_id_fkey",
        "matches",
        "stage_item_inputs",
        ["stage_item_input1_id", "tournament_id"],
        None,
    ),
    (
        "matches_stage_item_input2_id_fkey",
        "matches",
        "stage_item_inputs",
        ["stage_item_input2_id", "tournament_id"],
        None,
    ),
    (
        "stage_item_inputs_stage_item_id_fkey",
        "stage_item_inputs",
        "stage_items",
        ["stage_item_id", "tournament_id"],
        "CASCADE",
    ),
    (
        "stage_item_inputs_team_id_fkey",
        "stage_item_inputs",
        "teams",
        ["team_id", "tournament_id"],
        None,
    ),
    (
        "players_x_teams_player_id_fkey",
        "players_x_teams",
        "players",
        ["player_id", "tournament_id"],
        "CASCADE",
    ),
    (
        "players_x_teams_team_id_fkey",
        "players_x_teams",
        "teams",
        ["team_id", "tournament_id"],
        "CASCADE",
    ),
    (
        "stage_item_inputs_winner_from_stage_item_id_fkey",
        "stage_item_inputs",
        "stage_items",
        ["winner_from_stage_item_id", "tournament_id"],
        "SET NULL (winner_from_stage_item_id)",
    ),
    (
        "matches_stage_item_input1_winner_from_match_id_fkey",
        "matches",
        "matches",
        ["stage_item_input1_winner_from_match_id", "tournament_id"],
        "SET NULL (stage_item_input1_winner_from_match_id)",
    ),
    (
        "matches_stage_item_input2_winner_from_match_id_fkey",
        "matches",
        "matches",
        ["stage_item_input2_winner_from_match_id", "tournament_id"],
        "SET NULL (stage_item_input2_winner_from_match_id)",
    ),
]

SCOPED_TABLES = [
    "stages",
    "stage_items",
    "stage_item_inputs",
    "rounds",
    "matches",
    "teams",
    "players",
    "rankings",
]

NEW_SCOPE_COLUMNS = ("stage_items", "rounds", "matches", "players_x_teams")
NEW_INDEXES = (
    ("ix_rounds_stage_item_id", "rounds", "stage_item_id"),
    ("ix_matches_round_id", "matches", "round_id"),
    ("ix_players_x_teams_player_id", "players_x_teams", "player_id"),
    ("ix_users_x_clubs_user_id", "users_x_clubs", "user_id"),
)
ID_INDEX_TABLES = (
    "clubs",
    "tournaments",
    "stages",
    "stage_items",
    "stage_item_inputs",
    "rounds",
    "matches",
    "teams",
    "players",
    "users",
    "users_x_clubs",
    "players_x_teams",
    "rankings",
)


def _reject_rows(description: str, query: str) -> None:
    rows = op.get_bind().exec_driver_sql(query).fetchmany(10)
    if rows:
        examples = "; ".join(str(tuple(row)) for row in rows)
        raise RuntimeError(
            f"Cannot enforce tournament integrity: {description}. Affected rows: {examples}. "
            "Correct these records in the previous application version or database, then retry "
            "the upgrade. No records have been removed."
        )


def _validate_existing_data() -> None:
    for table, columns, predicate in (
        ("players_x_teams", "team_id, player_id", "TRUE"),
        ("stage_item_inputs", "stage_item_id, slot", "TRUE"),
        ("users_x_clubs", "club_id", "relation = 'OWNER'"),
    ):
        _reject_rows(
            f"duplicate {table} ({columns})",
            f"SELECT {columns}, array_agg(id ORDER BY id) FROM {table} "
            f"WHERE {predicate} GROUP BY {columns} HAVING count(*) > 1",
        )

    for description, query in (
        (
            "stage items and their rankings belong to different tournaments",
            (
                "SELECT si.id FROM stage_items si JOIN stages s ON s.id = si.stage_id "
                "JOIN rankings r ON r.id = si.ranking_id WHERE r.tournament_id <> s.tournament_id"
            ),
        ),
        (
            "slots and their stage items belong to different tournaments",
            (
                "SELECT i.id FROM stage_item_inputs i "
                "JOIN stage_items si ON si.id = i.stage_item_id "
                "JOIN stages s ON s.id = si.stage_id WHERE i.tournament_id <> s.tournament_id"
            ),
        ),
        (
            "slots and their teams belong to different tournaments",
            (
                "SELECT i.id FROM stage_item_inputs i JOIN teams t ON t.id = i.team_id "
                "WHERE i.tournament_id <> t.tournament_id"
            ),
        ),
        (
            "slots and their winner sources belong to different tournaments",
            (
                "SELECT i.id FROM stage_item_inputs i "
                "JOIN stage_items si ON si.id = i.winner_from_stage_item_id "
                "JOIN stages s ON s.id = si.stage_id WHERE i.tournament_id <> s.tournament_id"
            ),
        ),
        (
            "players and teams in a membership belong to different tournaments",
            (
                "SELECT pt.id FROM players_x_teams pt JOIN players p ON p.id = pt.player_id "
                "JOIN teams t ON t.id = pt.team_id WHERE p.tournament_id <> t.tournament_id"
            ),
        ),
        (
            "matches and their slots belong to different tournaments",
            (
                "SELECT m.id FROM matches m JOIN rounds r ON r.id = m.round_id "
                "JOIN stage_items si ON si.id = r.stage_item_id "
                "JOIN stages s ON s.id = si.stage_id "
                "JOIN stage_item_inputs i ON i.id IN "
                "(m.stage_item_input1_id, m.stage_item_input2_id) "
                "WHERE i.tournament_id <> s.tournament_id"
            ),
        ),
        (
            "matches and their winner sources belong to different tournaments",
            (
                "SELECT m.id FROM matches m JOIN rounds r ON r.id = m.round_id "
                "JOIN stage_items si ON si.id = r.stage_item_id "
                "JOIN stages s ON s.id = si.stage_id "
                "JOIN matches source ON source.id IN "
                "(m.stage_item_input1_winner_from_match_id, "
                "m.stage_item_input2_winner_from_match_id) "
                "JOIN rounds sr ON sr.id = source.round_id "
                "JOIN stage_items ssi ON ssi.id = sr.stage_item_id "
                "JOIN stages ss ON ss.id = ssi.stage_id WHERE ss.tournament_id <> s.tournament_id"
            ),
        ),
    ):
        _reject_rows(description, query)

    for table, constraints in CHECKS.items():
        for name, expression in constraints:
            _reject_rows(name, f"SELECT id FROM {table} WHERE NOT ({expression})")

    for table, columns in (
        ("rankings", ("win_points", "draw_points", "loss_points")),
        ("stage_item_inputs", ("points",)),
    ):
        for column in columns:
            _reject_rows(
                f"{table}.{column} cannot be represented exactly with six decimal places",
                f"SELECT id, {column} FROM {table} WHERE "
                f"{column}::text IN ('NaN', 'Infinity', '-Infinity') OR "
                f"abs({column}::numeric - round({column}::numeric, 6)) "
                f"> abs({column}::numeric) * 0.00000000000001 OR "
                f"abs({column}::numeric) >= 1000000000000000000",
            )


def upgrade() -> None:
    _validate_existing_data()
    for table in NEW_SCOPE_COLUMNS:
        op.add_column(table, sa.Column("tournament_id", sa.BigInteger(), nullable=True))
    op.execute(
        "UPDATE stage_items si SET tournament_id = s.tournament_id "
        "FROM stages s WHERE s.id = si.stage_id"
    )
    op.execute(
        "UPDATE rounds r SET tournament_id = si.tournament_id "
        "FROM stage_items si WHERE si.id = r.stage_item_id"
    )
    op.execute(
        "UPDATE matches m SET tournament_id = r.tournament_id FROM rounds r WHERE r.id = m.round_id"
    )
    op.execute(
        "UPDATE players_x_teams pt SET tournament_id = t.tournament_id "
        "FROM teams t WHERE t.id = pt.team_id"
    )
    for table in NEW_SCOPE_COLUMNS:
        op.alter_column(table, "tournament_id", nullable=False, existing_type=sa.BigInteger())
    for table in SCOPED_TABLES:
        op.create_unique_constraint(f"uq_{table}_id_tournament_id", table, ["id", "tournament_id"])
    for name, table, target, columns, ondelete in SCOPED_FOREIGN_KEYS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, target, columns, ["id", "tournament_id"], ondelete=ondelete
        )
    op.create_unique_constraint(
        "uq_players_x_teams_membership", "players_x_teams", ["team_id", "player_id"]
    )
    op.create_unique_constraint(
        "uq_stage_item_inputs_slot", "stage_item_inputs", ["stage_item_id", "slot"]
    )
    op.create_index(
        "uq_users_x_clubs_owner",
        "users_x_clubs",
        ["club_id"],
        unique=True,
        postgresql_where=sa.text("relation = 'OWNER'"),
    )
    for table, columns, precision in (
        ("rankings", ("win_points", "draw_points", "loss_points"), 12),
        ("stage_item_inputs", ("points",), 24),
    ):
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Float(),
                type_=sa.Numeric(precision, 6),
                postgresql_using=f"round({column}::numeric, 6)",
            )
    for table, constraints in CHECKS.items():
        for name, expression in constraints:
            op.create_check_constraint(name, table, expression)
    for name, table, column in NEW_INDEXES:
        op.create_index(name, table, [column])
    for table in ID_INDEX_TABLES:
        op.drop_index(f"ix_{table}_id", table_name=table)


def downgrade() -> None:
    for table in ID_INDEX_TABLES:
        op.create_index(f"ix_{table}_id", table, ["id"])
    for name, table, _ in reversed(NEW_INDEXES):
        op.drop_index(name, table_name=table)
    for table, constraints in CHECKS.items():
        for name, _ in constraints:
            op.drop_constraint(name, table, type_="check")
    for table, columns, precision in (
        ("rankings", ("win_points", "draw_points", "loss_points"), 12),
        ("stage_item_inputs", ("points",), 24),
    ):
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Numeric(precision, 6),
                type_=sa.Float(),
                postgresql_using=f"{column}::double precision",
            )
    op.drop_index("uq_users_x_clubs_owner", table_name="users_x_clubs")
    op.drop_constraint("uq_stage_item_inputs_slot", "stage_item_inputs", type_="unique")
    op.drop_constraint("uq_players_x_teams_membership", "players_x_teams", type_="unique")
    for index in range(len(SCOPED_FOREIGN_KEYS) - 1, -1, -1):
        name, table, target, columns, ondelete = SCOPED_FOREIGN_KEYS[index]
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            target,
            [columns[0]],
            ["id"],
            ondelete="SET NULL" if ondelete and ondelete.startswith("SET NULL") else ondelete,
        )
    for table in reversed(SCOPED_TABLES):
        op.drop_constraint(f"uq_{table}_id_tournament_id", table, type_="unique")
    for table in reversed(NEW_SCOPE_COLUMNS):
        op.drop_column(table, "tournament_id")
