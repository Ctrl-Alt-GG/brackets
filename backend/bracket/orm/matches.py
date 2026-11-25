from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bracket.orm.base import Base

if TYPE_CHECKING:
    from bracket.orm.stages import StageItemInput


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stage_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    matches: Mapped[list[Match]] = relationship(order_by="Match.id", lazy="raise", viewonly=True)

    __table_args__ = (
        UniqueConstraint("id", "tournament_id", name="uq_rounds_id_tournament_id"),
        ForeignKeyConstraint(
            ["stage_item_id", "tournament_id"],
            ["stage_items.id", "stage_items.tournament_id"],
            name="rounds_stage_item_id_fkey",
            ondelete="CASCADE",
        ),
        Index("ix_rounds_stage_item_id", "stage_item_id"),
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    custom_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_margin_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stage_item_input1_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stage_item_input2_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stage_item_input1_winner_from_match_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    stage_item_input2_winner_from_match_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    stage_item_input1_score: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_item_input2_score: Mapped[int] = mapped_column(Integer, nullable=False)
    scoreless_result: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    stage_item_input1: Mapped[StageItemInput | None] = relationship(
        foreign_keys=[stage_item_input1_id, tournament_id], lazy="raise", viewonly=True
    )
    stage_item_input2: Mapped[StageItemInput | None] = relationship(
        foreign_keys=[stage_item_input2_id, tournament_id], lazy="raise", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("id", "tournament_id", name="uq_matches_id_tournament_id"),
        ForeignKeyConstraint(
            ["round_id", "tournament_id"],
            ["rounds.id", "rounds.tournament_id"],
            name="matches_round_id_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["stage_item_input1_id", "tournament_id"],
            ["stage_item_inputs.id", "stage_item_inputs.tournament_id"],
            name="matches_stage_item_input1_id_fkey",
        ),
        ForeignKeyConstraint(
            ["stage_item_input2_id", "tournament_id"],
            ["stage_item_inputs.id", "stage_item_inputs.tournament_id"],
            name="matches_stage_item_input2_id_fkey",
        ),
        ForeignKeyConstraint(
            ["stage_item_input1_winner_from_match_id", "tournament_id"],
            ["matches.id", "matches.tournament_id"],
            name="matches_stage_item_input1_winner_from_match_id_fkey",
            ondelete="SET NULL (stage_item_input1_winner_from_match_id)",
        ),
        ForeignKeyConstraint(
            ["stage_item_input2_winner_from_match_id", "tournament_id"],
            ["matches.id", "matches.tournament_id"],
            name="matches_stage_item_input2_winner_from_match_id_fkey",
            ondelete="SET NULL (stage_item_input2_winner_from_match_id)",
        ),
        CheckConstraint(
            "stage_item_input1_score BETWEEN 0 AND 100000 "
            "AND stage_item_input2_score BETWEEN 0 AND 100000",
            name="ck_matches_scores",
        ),
        CheckConstraint(
            "NOT scoreless_result OR (stage_item_input1_score = 0 AND stage_item_input2_score = 0)",
            name="ck_matches_scoreless_result",
        ),
        CheckConstraint(
            "stage_item_input1_id IS NULL OR stage_item_input2_id IS NULL "
            "OR stage_item_input1_id <> stage_item_input2_id",
            name="ck_matches_distinct_inputs",
        ),
        CheckConstraint("duration_minutes BETWEEN 1 AND 1440", name="ck_matches_duration"),
        CheckConstraint("margin_minutes BETWEEN 0 AND 1440", name="ck_matches_margin"),
        CheckConstraint(
            "custom_duration_minutes IS NULL OR custom_duration_minutes BETWEEN 1 AND 1440",
            name="ck_matches_custom_duration",
        ),
        CheckConstraint(
            "custom_margin_minutes IS NULL OR custom_margin_minutes BETWEEN 0 AND 1440",
            name="ck_matches_custom_margin",
        ),
        Index("ix_matches_round_id", "round_id"),
    )
