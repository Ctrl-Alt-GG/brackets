from collections.abc import Iterator
from contextlib import contextmanager
from enum import auto

import asyncpg  # type: ignore[import-untyped]
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette import status

from bracket.utils.i18n import gettext, gettext_noop
from bracket.utils.types import EnumAutoStr


class UniqueIndex(EnumAutoStr):
    ix_tournaments_dashboard_endpoint_lower = auto()
    ix_users_email = auto()
    ix_users_email_lower = auto()
    stage_item_inputs_stage_item_id_team_id_key = auto()
    stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key = auto()
    tournament_organizers_pkey = auto()
    uq_tournament_organizers_owner = auto()
    tournament_players_pkey = auto()
    tournament_teams_pkey = auto()
    uq_stage_item_inputs_slot = auto()


class ForeignKey(EnumAutoStr):
    matches_stage_item_input1_id_fkey = auto()
    matches_stage_item_input2_id_fkey = auto()
    stage_item_inputs_team_id_fkey = auto()
    tournament_teams_team_id_fkey = auto()


unique_index_violation_error_lookup = {
    UniqueIndex.ix_tournaments_dashboard_endpoint_lower: gettext_noop(
        "This Details link is already taken"
    ),
    UniqueIndex.ix_users_email: gettext_noop("This email is already taken"),
    UniqueIndex.ix_users_email_lower: gettext_noop("This email is already taken"),
    # Both are unique per stage item: a team, or a place of an earlier stage item, takes one of
    # its slots at most.
    UniqueIndex.stage_item_inputs_stage_item_id_team_id_key: (
        gettext_noop("This team already has another slot in this stage item")
    ),
    UniqueIndex.stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key: (
        gettext_noop("This place is already taken by another slot of this stage item")
    ),
    UniqueIndex.tournament_organizers_pkey: gettext_noop(
        "This account already helps run this tournament"
    ),
    UniqueIndex.uq_tournament_organizers_owner: gettext_noop(
        "This tournament already has an owner"
    ),
    # A player is an active member of one team at most among the teams of a tournament.
    UniqueIndex.tournament_players_pkey: gettext_noop(
        "A player in these teams already plays for another team of the tournament"
    ),
    UniqueIndex.tournament_teams_pkey: gettext_noop(
        "This team already takes part in this tournament"
    ),
    UniqueIndex.uq_stage_item_inputs_slot: gettext_noop(
        "This slot is already part of this stage item"
    ),
}


foreign_key_violation_error_lookup = {
    ForeignKey.matches_stage_item_input1_id_fkey: gettext_noop(
        "This team is still part of matches"
    ),
    ForeignKey.matches_stage_item_input2_id_fkey: gettext_noop(
        "This team is still part of matches"
    ),
    ForeignKey.stage_item_inputs_team_id_fkey: (
        gettext_noop("This team still has a slot in a stage. Open that slot in Stages first.")
    ),
    ForeignKey.tournament_teams_team_id_fkey: gettext_noop(
        "This team takes part in a tournament. Remove it from the tournament first."
    ),
}


def unauthorized(detail: str | None = None) -> HTTPException:
    """For missing or invalid credentials. The frontend signs out when it gets this."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail or gettext("Could not validate credentials"),
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(detail: str) -> HTTPException:
    """
    For a valid session that may not do this. The frontend signs out on 401, which would end a
    session that is fine.
    """
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


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
            detail=gettext(unique_index_violation_error_lookup[constraint]),
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
            detail=gettext(foreign_key_violation_error_lookup[constraint]),
        ) from exc
