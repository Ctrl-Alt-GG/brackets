from collections.abc import Iterator
from contextlib import contextmanager
from enum import auto

import asyncpg  # type: ignore[import-untyped]
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette import status

from bracket.utils.types import EnumAutoStr


class UniqueIndex(EnumAutoStr):
    ix_tournaments_dashboard_endpoint_lower = auto()
    ix_users_email = auto()
    ix_users_email_lower = auto()
    stage_item_inputs_stage_item_id_team_id_key = auto()
    stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key = auto()
    users_x_clubs_club_id_user_id_key = auto()
    uq_users_x_clubs_owner = auto()
    uq_players_x_teams_membership = auto()
    uq_stage_item_inputs_slot = auto()


class ForeignKey(EnumAutoStr):
    matches_stage_item_input1_id_fkey = auto()
    matches_stage_item_input2_id_fkey = auto()
    stage_item_inputs_team_id_fkey = auto()
    tournaments_club_id_fkey = auto()


unique_index_violation_error_lookup = {
    UniqueIndex.ix_tournaments_dashboard_endpoint_lower: "This Details link is already taken",
    UniqueIndex.ix_users_email: "This email is already taken",
    UniqueIndex.ix_users_email_lower: "This email is already taken",
    # Both are unique per stage item: a team, or a place of an earlier stage item, takes one of
    # its slots at most.
    UniqueIndex.stage_item_inputs_stage_item_id_team_id_key: (
        "This team already has another slot in this stage item"
    ),
    UniqueIndex.stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key: (
        "This place is already taken by another slot of this stage item"
    ),
    UniqueIndex.users_x_clubs_club_id_user_id_key: "This account already helps run this event",
    UniqueIndex.uq_users_x_clubs_owner: "This event already has an owner",
    UniqueIndex.uq_players_x_teams_membership: "This player is already in this team",
    UniqueIndex.uq_stage_item_inputs_slot: "This slot is already part of this stage item",
}


foreign_key_violation_error_lookup = {
    ForeignKey.matches_stage_item_input1_id_fkey: "This team is still part of matches",
    ForeignKey.matches_stage_item_input2_id_fkey: "This team is still part of matches",
    ForeignKey.stage_item_inputs_team_id_fkey: (
        "This team still has a slot in a stage. Open that slot in Stages first."
    ),
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
        if constraint_name not in UniqueIndex.values():
            raise
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
        if constraint_name not in ForeignKey.values():
            raise
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
