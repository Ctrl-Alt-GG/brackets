from collections.abc import Iterator
from contextlib import contextmanager
from enum import auto

import asyncpg  # type: ignore[import-untyped]
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette import status

from bracket.utils.types import EnumAutoStr


class UniqueIndex(EnumAutoStr):
    ix_clubs_name = auto()
    ix_tournaments_dashboard_endpoint = auto()
    ix_users_email = auto()
    ix_users_email_lower = auto()
    stage_item_inputs_stage_item_id_team_id_key = auto()
    stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key = auto()


class ForeignKey(EnumAutoStr):
    matches_stage_item_input1_id_fkey = auto()
    matches_stage_item_input2_id_fkey = auto()
    stage_item_inputs_team_id_fkey = auto()
    tournaments_club_id_fkey = auto()


unique_index_violation_error_lookup = {
    UniqueIndex.ix_clubs_name: "This event name is already taken",
    UniqueIndex.ix_tournaments_dashboard_endpoint: "This Details link is already taken",
    UniqueIndex.ix_users_email: "This email is already taken",
    UniqueIndex.ix_users_email_lower: "This email is already taken",
    UniqueIndex.stage_item_inputs_stage_item_id_team_id_key: (
        "This team is already assigned to another stage item"
    ),
    UniqueIndex.stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key: (
        "This stage item winner is already assigned to another stage item"
    ),
}


foreign_key_violation_error_lookup = {
    ForeignKey.matches_stage_item_input1_id_fkey: "This team is still part of matches",
    ForeignKey.matches_stage_item_input2_id_fkey: "This team is still part of matches",
    ForeignKey.stage_item_inputs_team_id_fkey: "Invalid team as input to this stage item",
    ForeignKey.tournaments_club_id_fkey: "This event still has tournaments, delete those first",
}


def _postgres_error(exc: IntegrityError) -> BaseException | None:
    """The asyncpg error that SQLAlchemy wraps, which names the violated constraint."""
    return exc.orig.__cause__ if exc.orig is not None else None


@contextmanager
def check_unique_constraint_violation(expected_violations: set[UniqueIndex]) -> Iterator[None]:
    try:
        yield
    except IntegrityError as exc:
        error = _postgres_error(exc)
        if not isinstance(error, asyncpg.exceptions.UniqueViolationError):
            raise

        constraint_name = error.as_dict()["constraint_name"]
        assert constraint_name, "UniqueViolationError occurred but no constraint_name defined"
        assert constraint_name in UniqueIndex.values(), "Unknown UniqueViolationError occurred"
        constraint = UniqueIndex(constraint_name)

        if (
            constraint not in unique_index_violation_error_lookup
            or constraint not in expected_violations
        ):
            raise

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=unique_index_violation_error_lookup[constraint],
        ) from exc


@contextmanager
def check_foreign_key_violation(expected_violations: set[ForeignKey]) -> Iterator[None]:
    try:
        yield
    except IntegrityError as exc:
        error = _postgres_error(exc)
        if not isinstance(error, asyncpg.exceptions.ForeignKeyViolationError):
            raise

        constraint_name = error.as_dict()["constraint_name"]
        assert constraint_name, "ForeignKeyViolationError occurred but no constraint_name defined"
        assert constraint_name in ForeignKey.values(), (
            f"Unknown ForeignKeyViolationError occurred: {constraint_name}"
        )
        constraint = ForeignKey(constraint_name)

        if (
            constraint not in foreign_key_violation_error_lookup
            or constraint not in expected_violations
        ):
            raise

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=foreign_key_violation_error_lookup[constraint],
        ) from exc
