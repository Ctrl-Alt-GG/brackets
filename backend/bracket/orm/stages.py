from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bracket.models.db.stage_item import StageType
from bracket.orm.base import Base
from bracket.orm.types import StageTypeEnum

if TYPE_CHECKING:
    from bracket.orm.matches import Round
    from bracket.orm.participants import Team


class StageItem(Base):
    __tablename__ = "stage_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    stage_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    team_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ranking_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[StageType] = mapped_column(StageTypeEnum(), nullable=False)
    inputs: Mapped[list[StageItemInput]] = relationship(
        foreign_keys="[StageItemInput.stage_item_id, StageItemInput.tournament_id]",
        order_by="StageItemInput.slot",
        lazy="raise",
        viewonly=True,
    )
    rounds: Mapped[list[Round]] = relationship(order_by="Round.id", lazy="raise", viewonly=True)
    ranking: Mapped[Ranking] = relationship(lazy="raise", viewonly=True)

    @property
    def type_name(self) -> str:
        return self.type.value.lower().capitalize().replace("_", " ")

    __table_args__ = (
        UniqueConstraint("id", "tournament_id", name="uq_stage_items_id_tournament_id"),
        ForeignKeyConstraint(
            ["stage_id", "tournament_id"],
            ["stages.id", "stages.tournament_id"],
            name="stage_items_stage_id_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["ranking_id", "tournament_id"],
            ["rankings.id", "rankings.tournament_id"],
            name="stage_items_ranking_id_fkey",
            ondelete="CASCADE",
        ),
        CheckConstraint("team_count BETWEEN 2 AND 64", name="ck_stage_items_team_count"),
        CheckConstraint(
            "type <> 'SINGLE_ELIMINATION' OR team_count IN (2, 4, 8, 16, 32)",
            name="ck_stage_items_knockout_team_count",
        ),
    )


class StageItemInput(Base):
    __tablename__ = "stage_item_inputs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage_item_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    winner_from_stage_item_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    winner_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False, server_default="0")
    wins: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    draws: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    losses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    team: Mapped[Team | None] = relationship(lazy="raise", viewonly=True)

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
        UniqueConstraint("id", "tournament_id", name="uq_stage_item_inputs_id_tournament_id"),
        ForeignKeyConstraint(
            ["stage_item_id", "tournament_id"],
            ["stage_items.id", "stage_items.tournament_id"],
            name="stage_item_inputs_stage_item_id_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["team_id", "tournament_id"],
            ["teams.id", "teams.tournament_id"],
            name="stage_item_inputs_team_id_fkey",
        ),
        ForeignKeyConstraint(
            ["winner_from_stage_item_id", "tournament_id"],
            ["stage_items.id", "stage_items.tournament_id"],
            name="stage_item_inputs_winner_from_stage_item_id_fkey",
            ondelete="SET NULL (winner_from_stage_item_id)",
        ),
        CheckConstraint("slot BETWEEN 1 AND 64", name="ck_stage_item_inputs_slot"),
        CheckConstraint(
            "winner_position IS NULL OR winner_position BETWEEN 1 AND 64",
            name="ck_stage_item_inputs_winner_position",
        ),
        CheckConstraint(
            "wins >= 0 AND draws >= 0 AND losses >= 0", name="ck_stage_item_inputs_results"
        ),
        UniqueConstraint("stage_item_id", "slot", name="uq_stage_item_inputs_slot"),
    )


class Ranking(Base):
    __tablename__ = "rankings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tournament_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    win_points: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    draw_points: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    loss_points: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    add_score_points: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "tournament_id", name="uq_rankings_id_tournament_id"),
        CheckConstraint("position >= 0", name="ck_rankings_position"),
        CheckConstraint(
            "win_points BETWEEN -1000 AND 1000 AND draw_points BETWEEN -1000 AND 1000 "
            "AND loss_points BETWEEN -1000 AND 1000",
            name="ck_rankings_points",
        ),
    )
