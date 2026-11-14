from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from bracket.models.db.account import UserAccountType
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import TournamentStatus
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.orm.base import Base
from bracket.orm.types import StageTypeEnum


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    memberships: Mapped[list[UserXClub]] = relationship(
        back_populates="club", lazy="raise", passive_deletes=True
    )
    tournaments: Mapped[list[Tournament]] = relationship(lazy="raise", passive_deletes="all")


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    club_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clubs.id", name="tournaments_club_id_fkey"),
        index=True,
        nullable=False,
    )
    dashboard_public: Mapped[bool] = mapped_column(Boolean, nullable=False)
    logo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    dashboard_endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    players_can_be_in_multiple_teams: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="f"
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="15")
    margin_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    status: Mapped[TournamentStatus] = mapped_column(
        Enum(
            TournamentStatus,
            name="tournament_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default="OPEN",
        index=True,
    )
    matches_total: Mapped[int] = query_expression()
    matches_played: Mapped[int] = query_expression()
    last_match_end: Mapped[datetime | None] = query_expression()
    more_rounds_possible: Mapped[bool] = query_expression()

    __table_args__ = (
        Index(
            "ix_tournaments_dashboard_endpoint_lower", func.lower(dashboard_endpoint), unique=True
        ),
    )


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    custom_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_items: Mapped[list[StageItem]] = relationship(
        order_by="(StageItem.name, StageItem.id)", lazy="raise", passive_deletes=True
    )


class StageItem(Base):
    __tablename__ = "stage_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    stage_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ranking_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rankings.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[StageType] = mapped_column(StageTypeEnum(), nullable=False)
    inputs: Mapped[list[StageItemInput]] = relationship(
        foreign_keys="StageItemInput.stage_item_id",
        order_by="StageItemInput.slot",
        lazy="raise",
        passive_deletes=True,
    )
    rounds: Mapped[list[Round]] = relationship(
        order_by="Round.id", lazy="raise", passive_deletes=True
    )
    ranking: Mapped[Ranking] = relationship(lazy="raise")

    @property
    def type_name(self) -> str:
        return self.type.value.lower().capitalize().replace("_", " ")


class StageItemInput(Base):
    __tablename__ = "stage_item_inputs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stage_items.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("teams.id", name="stage_item_inputs_team_id_fkey"), nullable=True
    )
    winner_from_stage_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stage_items.id", ondelete="SET NULL"), nullable=True
    )
    winner_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    wins: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    draws: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    losses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    team: Mapped[Team | None] = relationship(lazy="raise")

    __table_args__ = (
        UniqueConstraint(
            "stage_item_id", "team_id", name="stage_item_inputs_stage_item_id_team_id_key"
        ),
        UniqueConstraint(
            "stage_item_id",
            "winner_from_stage_item_id",
            "winner_position",
            name="stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key",
        ),
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stage_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stage_items.id", ondelete="CASCADE"), nullable=False
    )
    matches: Mapped[list[Match]] = relationship(
        order_by="Match.id", lazy="raise", passive_deletes=True
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    margin_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_margin_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
    )
    stage_item_input1_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("stage_item_inputs.id", name="matches_stage_item_input1_id_fkey"),
        nullable=True,
    )
    stage_item_input2_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("stage_item_inputs.id", name="matches_stage_item_input2_id_fkey"),
        nullable=True,
    )
    stage_item_input1_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stage_item_input2_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stage_item_input1_winner_from_match_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True
    )
    stage_item_input2_winner_from_match_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True
    )
    stage_item_input1_score: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_item_input2_score: Mapped[int] = mapped_column(Integer, nullable=False)
    scoreless_result: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    stage_item_input1: Mapped[StageItemInput | None] = relationship(
        foreign_keys=[stage_item_input1_id], lazy="raise"
    )
    stage_item_input2: Mapped[StageItemInput | None] = relationship(
        foreign_keys=[stage_item_input2_id], lazy="raise"
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
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


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
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


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    account_type: Mapped[UserAccountType] = mapped_column(
        Enum(UserAccountType, name="account_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    memberships: Mapped[list[UserXClub]] = relationship(
        back_populates="user", lazy="raise", passive_deletes=True
    )

    __table_args__ = (Index("ix_users_email_lower", func.lower(email), unique=True),)


class RevokedSession(Base):
    __tablename__ = "revoked_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class UserXClub(Base):
    __tablename__ = "users_x_clubs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[UserXClubRelation] = mapped_column(
        Enum(
            UserXClubRelation,
            name="user_x_club_relation",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=UserXClubRelation.OWNER,
    )
    club: Mapped[Club] = relationship(back_populates="memberships", lazy="raise")
    user: Mapped[User] = relationship(back_populates="memberships", lazy="raise")

    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="users_x_clubs_club_id_user_id_key"),
    )


class PlayerXTeam(Base):
    __tablename__ = "players_x_teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )


class Ranking(Base):
    __tablename__ = "rankings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    win_points: Mapped[float] = mapped_column(Float, nullable=False)
    draw_points: Mapped[float] = mapped_column(Float, nullable=False)
    loss_points: Mapped[float] = mapped_column(Float, nullable=False)
    add_score_points: Mapped[bool] = mapped_column(Boolean, nullable=False)
