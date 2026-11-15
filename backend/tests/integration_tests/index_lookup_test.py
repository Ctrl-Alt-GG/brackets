import pytest
from sqlalchemy import UniqueConstraint, text
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.utils.errors import (
    foreign_key_violation_error_lookup,
    unique_index_violation_error_lookup,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_all_unique_indices_in_lookup(session: AsyncSession) -> None:
    query = """
    SELECT
        idx.relname AS index_name
    FROM pg_index pgi
        JOIN pg_class idx ON idx.oid = pgi.indexrelid
        JOIN pg_namespace insp ON insp.oid = idx.relnamespace
        JOIN pg_class tbl ON tbl.oid = pgi.indrelid
        JOIN pg_namespace tnsp ON tnsp.oid = tbl.relnamespace
    WHERE pgi.indisunique
        AND tnsp.nspname = 'public'
        AND idx.relname NOT LIKE '%_pkey'
        AND idx.relname !='alembic_version_pkc'
    """
    result = await session.execute(text(query))
    indices = {ix.index_name for ix in result}

    expected_indices = {ix.name for ix in unique_index_violation_error_lookup.keys()}
    # Supporting composite foreign keys need unique parent keys as well as public uniqueness rules.
    metadata_indices = {
        index.name
        for table in orm.Base.metadata.tables.values()
        for index in table.indexes
        if index.unique
    } | {
        constraint.name
        for table in orm.Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert indices == metadata_indices
    assert expected_indices <= indices


@pytest.mark.asyncio(loop_scope="session")
async def test_known_foreign_keys_in_lookup(session: AsyncSession) -> None:
    query = """
        SELECT conrelid::regclass AS table_name,
               conname AS foreign_key
        FROM   pg_constraint
        WHERE  contype = 'f'
        AND    connamespace = 'public'::regnamespace
        ORDER  BY conrelid::regclass::text, contype DESC;
    """
    result = await session.execute(text(query))
    indices = {ix.foreign_key for ix in result}

    for foreign_key in foreign_key_violation_error_lookup.keys():
        msg = f"Unexpected foreign key in lookup: {foreign_key.value}"
        assert foreign_key.name in indices, msg
