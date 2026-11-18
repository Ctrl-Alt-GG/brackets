from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from bracket import orm
from bracket.utils.uploads import StoredUpload, UploadFolder

# The column that refers to the files of each folder.
REFERENCES: dict[UploadFolder, InstrumentedAttribute[str | None]] = {
    UploadFolder.TEAM_LOGOS: orm.Team.logo_path,
    UploadFolder.TOURNAMENT_LOGOS: orm.Tournament.logo_path,
}


async def get_referenced_uploads(
    session: AsyncSession, uploads: Collection[StoredUpload]
) -> set[StoredUpload]:
    """Those of the uploads that a team or tournament refers to."""
    referenced: set[StoredUpload] = set()
    for folder, column in REFERENCES.items():
        in_folder = [upload for upload in uploads if upload.folder is folder]
        if in_folder:
            found = set(
                await session.scalars(
                    select(column).where(column.in_([upload.filename for upload in in_folder]))
                )
            )
            referenced.update(upload for upload in in_folder if upload.filename in found)
    return referenced
