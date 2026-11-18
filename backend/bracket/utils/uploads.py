from __future__ import annotations

import mimetypes
import warnings
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import aiofiles
import aiofiles.os
from anyio import CapacityLimiter, to_thread
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from bracket.config import config

# Pillow registers formats lazily; this loads the common ones, including PNG and JPEG.
Image.preinit()
# Refuse images Pillow considers decompression bombs instead of only warning. Set once here, as
# images are processed in worker threads, where changing the warning filters per call would race.
warnings.filterwarnings("error", category=Image.DecompressionBombWarning)
# Pillow's names of the image formats that can be uploaded.
UPLOADABLE_IMAGE_FORMATS = frozenset({"PNG", "JPEG"})
UPLOADABLE_MEDIA_TYPES = frozenset(
    Image.MIME[image_format] for image_format in UPLOADABLE_IMAGE_FORMATS
)
# Logos are shown small. Larger uploads are scaled down to fit this box.
MAX_LOGO_SIZE = (512, 512)
# Bound memory before Pillow loads the full bitmap. Compressed byte size alone does not.
MAX_LOGO_INPUT_DIMENSION = 4096
MAX_LOGO_INPUT_PIXELS = 4_000_000
IMAGE_TOO_LARGE_MESSAGE = "Image is too large. Use at most 4096 pixels per side and 4 megapixels."
# Decoding and encoding an image takes a while and holds its bitmap in memory. Requests do it in
# worker threads, so the server keeps answering everyone else, and only a few at a time.
IMAGE_PROCESSING = CapacityLimiter(2)
NEW_UPLOADS = "new_uploads"


class UploadFolder(StrEnum):
    TEAM_LOGOS = "team-logos"
    TOURNAMENT_LOGOS = "tournament-logos"


def build_upload_path(folder: UploadFolder, filename: str) -> Path:
    return Path(config.upload_dir) / folder / filename


@dataclass(frozen=True)
class StoredUpload:
    """
    A file a command stored, which only stays if the command's transaction commits: see
    `bracket.database.session_scope`.
    """

    folder: UploadFolder
    filename: str

    @property
    def path(self) -> Path:
        return build_upload_path(self.folder, self.filename)


def new_uploads(session: AsyncSession) -> list[StoredUpload]:
    """The files stored for this transaction, which its owner keeps only when it commits."""
    uploads: list[StoredUpload] = session.info.setdefault(NEW_UPLOADS, [])
    return uploads


def get_image_media_type(filename: str) -> str:
    media_type, _ = mimetypes.guess_type(filename)
    if media_type not in UPLOADABLE_MEDIA_TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unsupported logo type")
    return media_type


async def get_existing_upload_path(folder: UploadFolder, filename: str | None) -> Path | None:
    if not filename:
        return None

    path = build_upload_path(folder, filename)
    return path if await aiofiles.os.path.exists(str(path)) else None


async def get_logo_response(folder: UploadFolder, filename: str | None) -> FileResponse:
    path = await get_existing_upload_path(folder, filename)
    if filename is None or path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo not found")

    return FileResponse(path, media_type=get_image_media_type(filename))


async def remove_existing_upload(folder: UploadFolder, filename: str | None) -> None:
    """Remove the file, if it is still there."""
    if filename:
        with suppress(FileNotFoundError):
            await aiofiles.os.remove(str(build_upload_path(folder, filename)))


async def remove_existing_uploads(folder: UploadFolder, filenames: list[str | None]) -> None:
    for filename in filenames:
        await remove_existing_upload(folder, filename)


async def store_validated_image_upload(
    file: UploadFile, folder: UploadFolder, session: AsyncSession
) -> StoredUpload:
    """
    Store the image as `normalize_image` makes it, for the transaction of `session`: the file
    stays only if that commits.
    """
    content = await file.read(config.upload_max_bytes + 1)
    if len(content) > config.upload_max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Uploaded file exceeds the {config.upload_max_bytes}-byte limit",
        )

    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")

    normalized = await to_thread.run_sync(normalize_image, content, limiter=IMAGE_PROCESSING)
    if normalized is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only PNG and JPEG image uploads are supported",
        )

    image_format, image_content = normalized
    upload = StoredUpload(folder, f"{uuid4()}{mimetypes.guess_extension(Image.MIME[image_format])}")
    # Registered before the file exists, so that a write that fails or is cancelled halfway is
    # removed with the transaction too.
    new_uploads(session).append(upload)
    await aiofiles.os.makedirs(str(upload.path.parent), exist_ok=True)
    async with aiofiles.open(upload.path, "wb") as file_handle:
        await file_handle.write(image_content)
    return upload


def sniff_image_format(content: bytes) -> str | None:
    normalized = normalize_image(content)
    return normalized[0] if normalized is not None else None


def normalize_image(content: bytes) -> tuple[str, bytes] | None:
    """
    The image as it is stored: decoded, turned upright, scaled down to logo size and encoded
    again. `None` for anything that isn't a PNG or JPEG image.

    Encoding it again drops what a camera or editor put in the file besides the picture, such
    as where a photo was taken, and guarantees that the stored bytes are only an image.
    """
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            if image_format not in UPLOADABLE_IMAGE_FORMATS:
                return None

            if (
                max(image.size) > MAX_LOGO_INPUT_DIMENSION
                or image.width * image.height > MAX_LOGO_INPUT_PIXELS
            ):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    IMAGE_TOO_LARGE_MESSAGE,
                )

            # Decodes the image, which also fails for a file that only claims to be one.
            upright = ImageOps.exif_transpose(image)
            upright.thumbnail(MAX_LOGO_SIZE)

            output = BytesIO()
            if image_format == "JPEG":
                upright.convert("RGB").save(output, format="JPEG", quality=88, optimize=True)
            else:
                upright.save(output, format="PNG", optimize=True)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, IMAGE_TOO_LARGE_MESSAGE) from exc
    except (UnidentifiedImageError, OSError, ValueError):
        return None

    assert isinstance(image_format, str)
    return image_format, output.getvalue()
