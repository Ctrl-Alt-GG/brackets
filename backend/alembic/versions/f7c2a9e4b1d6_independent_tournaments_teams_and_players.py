"""Remove events; make tournaments, teams and players independent of each other.

- Events (`clubs`) are gone. Who ran an event now runs each of its tournaments: its owner owns
  them, and its other organizers help (`tournament_organizers`).
- Teams and players no longer belong to a tournament. A team takes part in the tournament it
  belonged to (`tournament_teams`, which keeps its `active` flag), and its roster becomes
  `team_members`. A member is active unless the player was marked inactive. A player can be an
  active member of one team per tournament, so one that was in several teams of a tournament
  (`players_can_be_in_multiple_teams`) stays active in the team they joined first only.
- `tournament_players` records which team each player plays for in a tournament, filled from the
  active members, archived tournaments included.
- Matches lose their stored conflict flags, and teams and players their unused result columns:
  conflicts are worked out when the schedule is shown, results are replayed from the matches.

A downgrade gives every tournament an event of its own, with the same organizers. It needs every
team to take part in exactly one tournament and every player to be in the teams of exactly one, as
before this revision.

Revision ID: f7c2a9e4b1d6
Revises: e1d4f7a2b9c3
Create Date: 2026-11-25 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "f7c2a9e4b1d6"
down_revision: str = "e1d4f7a2b9c3"
branch_labels: str | None = None
depends_on: str | None = None

PARTICIPANT_TABLES = ("teams", "players")
RESULT_COLUMNS = ("elo_score", "swiss_score", "wins", "draws", "losses")


def upgrade() -> None:
    _create_tournament_organizers()
    _create_participations()
    _drop_events()
    _drop_tournament_scope_of_participants()
    for position in (1, 2):
        op.drop_column("matches", f"stage_item_input{position}_conflict")


def _create_tournament_organizers() -> None:
    op.create_table(
        "tournament_organizers",
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Enum("OWNER", "COLLABORATOR", name="tournament_role"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name="tournament_organizers_tournament_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="tournament_organizers_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tournament_id", "user_id", name="tournament_organizers_pkey"),
    )
    op.create_index("ix_tournament_organizers_user_id", "tournament_organizers", ["user_id"])
    op.create_index(
        "uq_tournament_organizers_owner",
        "tournament_organizers",
        ["tournament_id"],
        unique=True,
        postgresql_where=sa.text("role = 'OWNER'"),
    )
    op.execute(
        "INSERT INTO tournament_organizers (tournament_id, user_id, role) "
        "SELECT t.id, m.user_id, m.relation::text::tournament_role "
        "FROM tournaments t JOIN users_x_clubs m ON m.club_id = t.club_id"
    )


def _create_participations() -> None:
    op.create_table(
        "tournament_teams",
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name="tournament_teams_tournament_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="tournament_teams_team_id_fkey"),
        sa.PrimaryKeyConstraint("tournament_id", "team_id", name="tournament_teams_pkey"),
    )
    op.create_index("ix_tournament_teams_team_id", "tournament_teams", ["team_id"])
    op.execute(
        "INSERT INTO tournament_teams (tournament_id, team_id, active) "
        "SELECT tournament_id, id, active FROM teams"
    )

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="team_members_team_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="team_members_player_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("team_id", "player_id", name="team_members_pkey"),
    )
    op.create_index("ix_team_members_player_id", "team_members", ["player_id"])
    # A player's memberships were all in the teams of their tournament.
    op.execute(
        "INSERT INTO team_members (team_id, player_id, active) "
        "SELECT team_id, player_id, active AND joined_first FROM ("
        "SELECT pt.team_id, pt.player_id, p.active, "
        "row_number() OVER (PARTITION BY pt.player_id ORDER BY pt.id) = 1 AS joined_first "
        "FROM players_x_teams pt JOIN players p ON p.id = pt.player_id"
        ") AS memberships"
    )

    op.create_table(
        "tournament_players",
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tournament_id", "team_id"],
            ["tournament_teams.tournament_id", "tournament_teams.team_id"],
            name="tournament_players_team_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="tournament_players_player_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tournament_id", "player_id", name="tournament_players_pkey"),
    )
    op.create_index("ix_tournament_players_player_id", "tournament_players", ["player_id"])
    op.execute(
        "INSERT INTO tournament_players (tournament_id, player_id, team_id) "
        "SELECT tt.tournament_id, m.player_id, m.team_id "
        "FROM tournament_teams tt JOIN team_members m ON m.team_id = tt.team_id WHERE m.active"
    )

    op.drop_constraint("stage_item_inputs_team_id_fkey", "stage_item_inputs", type_="foreignkey")
    op.create_foreign_key(
        "stage_item_inputs_team_id_fkey",
        "stage_item_inputs",
        "tournament_teams",
        ["tournament_id", "team_id"],
        ["tournament_id", "team_id"],
    )


def _drop_events() -> None:
    op.drop_constraint("tournaments_club_id_fkey", "tournaments", type_="foreignkey")
    op.drop_index("ix_tournaments_club_id", table_name="tournaments")
    op.drop_column("tournaments", "club_id")
    op.drop_column("tournaments", "players_can_be_in_multiple_teams")
    op.drop_table("users_x_clubs")
    op.drop_table("clubs")
    sa.Enum(name="user_x_club_relation").drop(op.get_bind())


def _drop_tournament_scope_of_participants() -> None:
    op.drop_table("players_x_teams")
    for table in PARTICIPANT_TABLES:
        op.drop_constraint(f"{table}_tournament_id_fkey", table, type_="foreignkey")
        op.drop_constraint(f"uq_{table}_id_tournament_id", table, type_="unique")
        op.drop_constraint(f"ck_{table}_results", table, type_="check")
        op.drop_index(f"ix_{table}_tournament_id", table_name=table)
        op.drop_index(f"ix_{table}_active", table_name=table)
        for column in ("tournament_id", "active", *RESULT_COLUMNS):
            op.drop_column(table, column)


def downgrade() -> None:
    _reject_rows(
        "teams that take part in no tournament or in several",
        "SELECT t.id, t.name FROM teams t LEFT JOIN tournament_teams tt ON tt.team_id = t.id "
        "GROUP BY t.id HAVING count(tt.tournament_id) <> 1",
    )
    _reject_rows(
        "players who are in the teams of no tournament or of several",
        "SELECT p.id, p.name FROM players p "
        "LEFT JOIN team_members m ON m.player_id = p.id "
        "LEFT JOIN tournament_teams tt ON tt.team_id = m.team_id "
        "GROUP BY p.id HAVING count(DISTINCT tt.tournament_id) <> 1",
    )
    for position in (1, 2):
        column = f"stage_item_input{position}_conflict"
        op.add_column("matches", sa.Column(column, sa.Boolean(), server_default="false"))
        op.alter_column("matches", column, nullable=False, server_default=None)
    _restore_tournament_scope_of_participants()
    _restore_events()
    op.drop_table("tournament_players")
    op.drop_table("team_members")
    op.drop_table("tournament_teams")
    op.drop_table("tournament_organizers")
    sa.Enum(name="tournament_role").drop(op.get_bind())


def _reject_rows(description: str, query: str) -> None:
    rows = op.get_bind().exec_driver_sql(query).fetchmany(10)
    if rows:
        examples = "; ".join(str(tuple(row)) for row in rows)
        raise RuntimeError(
            f"Cannot downgrade: the previous schema can't hold {description}. Affected rows: "
            f"{examples}. Remove those teams from tournaments, or those players from teams, "
            "until each belongs to one tournament, then retry. No records have been removed."
        )


def _restore_tournament_scope_of_participants() -> None:
    op.add_column("teams", sa.Column("tournament_id", sa.BigInteger()))
    op.add_column("teams", sa.Column("active", sa.Boolean(), server_default="true"))
    op.execute(
        "UPDATE teams SET tournament_id = tt.tournament_id, active = tt.active "
        "FROM tournament_teams tt WHERE tt.team_id = teams.id"
    )
    op.add_column("players", sa.Column("tournament_id", sa.BigInteger()))
    op.add_column("players", sa.Column("active", sa.Boolean(), server_default="true"))
    op.execute(
        "UPDATE players SET tournament_id = memberships.tournament_id, "
        "active = memberships.active FROM ("
        "SELECT m.player_id, min(tt.tournament_id) AS tournament_id, bool_or(m.active) AS active "
        "FROM team_members m JOIN tournament_teams tt ON tt.team_id = m.team_id "
        "GROUP BY m.player_id"
        ") AS memberships WHERE memberships.player_id = players.id"
    )
    for table in PARTICIPANT_TABLES:
        op.alter_column(table, "tournament_id", nullable=False)
        op.alter_column(table, "active", nullable=False)
        # Never written: results are replayed from the matches.
        for column, type_ in (
            ("elo_score", sa.Float()),
            ("swiss_score", sa.Float()),
            ("wins", sa.Integer()),
            ("draws", sa.Integer()),
            ("losses", sa.Integer()),
        ):
            op.add_column(table, sa.Column(column, type_, server_default="0", nullable=False))
            if table == "players":
                op.alter_column(table, column, server_default=None)
        op.create_check_constraint(
            f"ck_{table}_results", table, "wins >= 0 AND draws >= 0 AND losses >= 0"
        )
        op.create_index(f"ix_{table}_tournament_id", table, ["tournament_id"])
        op.create_index(f"ix_{table}_active", table, ["active"])
        op.create_unique_constraint(f"uq_{table}_id_tournament_id", table, ["id", "tournament_id"])
        op.create_foreign_key(
            f"{table}_tournament_id_fkey",
            table,
            "tournaments",
            ["tournament_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_table(
        "players_x_teams",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id", "tournament_id"],
            ["players.id", "players.tournament_id"],
            name="players_x_teams_player_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "tournament_id"],
            ["teams.id", "teams.tournament_id"],
            name="players_x_teams_team_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="players_x_teams_pkey"),
        sa.UniqueConstraint("team_id", "player_id", name="uq_players_x_teams_membership"),
    )
    op.create_index("ix_players_x_teams_player_id", "players_x_teams", ["player_id"])
    op.execute(
        "INSERT INTO players_x_teams (player_id, team_id, tournament_id) "
        "SELECT m.player_id, m.team_id, tt.tournament_id "
        "FROM team_members m JOIN tournament_teams tt ON tt.team_id = m.team_id "
        "ORDER BY m.team_id, m.player_id"
    )

    op.drop_constraint("stage_item_inputs_team_id_fkey", "stage_item_inputs", type_="foreignkey")
    op.create_foreign_key(
        "stage_item_inputs_team_id_fkey",
        "stage_item_inputs",
        "teams",
        ["team_id", "tournament_id"],
        ["id", "tournament_id"],
    )


def _restore_events() -> None:
    op.create_table(
        "clubs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="clubs_pkey"),
    )
    op.create_index("ix_clubs_name", "clubs", ["name"])
    # Every tournament gets an event of its own, which takes its id and name.
    op.execute("INSERT INTO clubs (id, name, created) SELECT id, name, created FROM tournaments")
    op.execute(
        "SELECT setval(pg_get_serial_sequence('clubs', 'id'), "
        "coalesce((SELECT max(id) FROM clubs), 0) + 1, false)"
    )

    op.create_table(
        "users_x_clubs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("club_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "relation",
            sa.Enum("OWNER", "COLLABORATOR", name="user_x_club_relation"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], name="users_x_clubs_club_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="users_x_clubs_user_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="users_x_clubs_pkey"),
        sa.UniqueConstraint("club_id", "user_id", name="users_x_clubs_club_id_user_id_key"),
    )
    op.create_index("ix_users_x_clubs_user_id", "users_x_clubs", ["user_id"])
    op.create_index(
        "uq_users_x_clubs_owner",
        "users_x_clubs",
        ["club_id"],
        unique=True,
        postgresql_where=sa.text("relation = 'OWNER'"),
    )
    op.execute(
        "INSERT INTO users_x_clubs (club_id, user_id, relation) "
        "SELECT tournament_id, user_id, role::text::user_x_club_relation "
        "FROM tournament_organizers ORDER BY tournament_id, user_id"
    )

    op.add_column("tournaments", sa.Column("club_id", sa.BigInteger()))
    op.execute("UPDATE tournaments SET club_id = id")
    op.alter_column("tournaments", "club_id", nullable=False)
    op.create_index("ix_tournaments_club_id", "tournaments", ["club_id"])
    op.create_foreign_key("tournaments_club_id_fkey", "tournaments", "clubs", ["club_id"], ["id"])

    op.add_column(
        "tournaments",
        sa.Column(
            "players_can_be_in_multiple_teams",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    # Tournaments with players in several of their teams allowed that before.
    op.execute(
        "UPDATE tournaments SET players_can_be_in_multiple_teams = true WHERE id IN ("
        "SELECT tournament_id FROM players_x_teams "
        "GROUP BY tournament_id, player_id HAVING count(*) > 1)"
    )
