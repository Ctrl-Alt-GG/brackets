from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bracket.orm.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default="t")
    elo_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    swiss_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    wins: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    draws: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    losses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    logo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    players: Mapped[list[Player]] = relationship(
        secondary="players_x_teams",
        order_by="(Player.name, Player.id)",
        lazy="raise",
        viewonly=True,
    )

    __table_args__ = (
        UniqueConstraint("id", "tournament_id", name="uq_teams_id_tournament_id"),
        CheckConstraint("wins >= 0 AND draws >= 0 AND losses >= 0", name="ck_teams_results"),
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    elo_score: Mapped[float] = mapped_column(Float, nullable=False)
    swiss_score: Mapped[float] = mapped_column(Float, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, nullable=False)
    draws: Mapped[int] = mapped_column(Integer, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default="t")

    __table_args__ = (
        UniqueConstraint("id", "tournament_id", name="uq_players_id_tournament_id"),
        CheckConstraint("wins >= 0 AND draws >= 0 AND losses >= 0", name="ck_players_results"),
    )


class PlayerXTeam(Base):
    __tablename__ = "players_x_teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["player_id", "tournament_id"],
            ["players.id", "players.tournament_id"],
            name="players_x_teams_player_id_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["team_id", "tournament_id"],
            ["teams.id", "teams.tournament_id"],
            name="players_x_teams_team_id_fkey",
            ondelete="CASCADE",
        ),
        UniqueConstraint("team_id", "player_id", name="uq_players_x_teams_membership"),
        Index("ix_players_x_teams_player_id", "player_id"),
    )
