from __future__ import annotations

import mimetypes
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import aiofiles
import aiofiles.os
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from bracket.config import config

# Pillow registers formats lazily; this loads the common ones, including PNG and JPEG.
Image.preinit()
# Pillow's names of the image formats that can be uploaded.
UPLOADABLE_IMAGE_FORMATS = frozenset({"PNG", "JPEG"})
UPLOADABLE_MEDIA_TYPES = frozenset(
    Image.MIME[image_format] for image_format in UPLOADABLE_IMAGE_FORMATS
)


def build_upload_path(folder: str, filename: str) -> Path:
    return Path(config.upload_dir) / folder / filename


def get_image_media_type(filename: str) -> str:
    media_type, _ = mimetypes.guess_type(filename)
    if media_type not in UPLOADABLE_MEDIA_TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unsupported logo type")
    return media_type


async def get_existing_upload_path(folder: str, filename: str | None) -> Path | None:
    if not filename:
        return None

    path = build_upload_path(folder, filename)
    return path if await aiofiles.os.path.exists(str(path)) else None


async def remove_existing_upload(folder: str, filename: str | None) -> None:
    path = await get_existing_upload_path(folder, filename)
    if path is not None:
        await aiofiles.os.remove(str(path))


async def store_validated_image_upload(file: UploadFile, folder: str) -> str:
    content = await file.read(config.upload_max_bytes + 1)
    if len(content) > config.upload_max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Uploaded file exceeds the {config.upload_max_bytes}-byte limit",
        )

    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")

    image_format = sniff_image_format(content)
    if image_format is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only PNG and JPEG image uploads are supported",
        )

    filename = f"{uuid4()}{mimetypes.guess_extension(Image.MIME[image_format])}"
    upload_path = build_upload_path(folder, filename)
    await aiofiles.os.makedirs(str(upload_path.parent), exist_ok=True)
    async with aiofiles.open(upload_path, "wb") as file_handle:
        await file_handle.write(content)
    return filename


def sniff_image_format(content: bytes) -> str | None:
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError):
        return None

    if not isinstance(image_format, str):
        return None

    if image_format not in UPLOADABLE_IMAGE_FORMATS:
        return None

    return image_format
