"""
Teams and players, and how they take part in tournaments.

Teams and players are shared by every tournament. A team takes part in a tournament through a
`TournamentTeam`. Its roster is its `TeamMember`s, of whom the active ones play. A tournament's
lineup, its `TournamentPlayer`s, says which team every player plays for in it. Its primary key is
the rule that a player is an active member of one team at most among the teams of a tournament.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bracket.orm.base import Base

if TYPE_CHECKING:
    from bracket.orm.tournaments import Tournament


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    logo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    members: Mapped[list[TeamMember]] = relationship(lazy="raise", viewonly=True)
    participations: Mapped[list[TournamentTeam]] = relationship(
        order_by="TournamentTeam.tournament_id", lazy="raise", viewonly=True
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TeamMember(Base):
    """A player in a team's roster."""

    __tablename__ = "team_members"

    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    player: Mapped[Player] = relationship(lazy="raise", viewonly=True)

    __table_args__ = (Index("ix_team_members_player_id", "player_id"),)


class TournamentTeam(Base):
    """
    A team that takes part in a tournament. A team that takes part anywhere can't be deleted, and
    one that has a slot in a stage can't leave the tournament.
    """

    __tablename__ = "tournament_teams"

    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.id", name="tournament_teams_team_id_fkey"), primary_key=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    team: Mapped[Team] = relationship(lazy="raise", viewonly=True)
    tournament: Mapped[Tournament] = relationship(lazy="raise", viewonly=True)
    players: Mapped[list[Player]] = relationship(
        secondary="tournament_players",
        primaryjoin="and_(TournamentTeam.tournament_id == TournamentPlayer.tournament_id, "
        "TournamentTeam.team_id == TournamentPlayer.team_id)",
        secondaryjoin="Player.id == TournamentPlayer.player_id",
        order_by="(Player.name, Player.id)",
        lazy="raise",
        viewonly=True,
    )

    __table_args__ = (Index("ix_tournament_teams_team_id", "team_id"),)


class TournamentPlayer(Base):
    """
    A player in a tournament's lineup, and the team they play for in it.

    The lineups of open tournaments follow the active members of their teams. Archiving a
    tournament keeps its lineups as they were, so later changes of a roster don't rewrite who
    played in it.
    """

    __tablename__ = "tournament_players"

    tournament_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tournament_id", "team_id"],
            ["tournament_teams.tournament_id", "tournament_teams.team_id"],
            name="tournament_players_team_fkey",
            ondelete="CASCADE",
        ),
        Index("ix_tournament_players_player_id", "player_id"),
    )
