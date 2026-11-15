from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from bracket.models.db.tournament import TournamentStatus
from bracket.orm.base import Base

if TYPE_CHECKING:
    from bracket.orm.stages import StageItem


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
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
        CheckConstraint("duration_minutes BETWEEN 1 AND 1440", name="ck_tournaments_duration"),
        CheckConstraint("margin_minutes BETWEEN 0 AND 1440", name="ck_tournaments_margin"),
    )


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
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
        order_by="(StageItem.name, StageItem.id)", lazy="raise", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("id", "tournament_id", name="uq_stages_id_tournament_id"),
        CheckConstraint(
            "custom_duration_minutes IS NULL OR custom_duration_minutes BETWEEN 1 AND 1440",
            name="ck_stages_custom_duration",
        ),
    )
