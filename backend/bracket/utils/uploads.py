from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import aiofiles
import aiofiles.os
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from bracket.config import config

IMAGE_FORMAT_TO_EXTENSION = {
    "PNG": ".png",
    "JPEG": ".jpg",
}

IMAGE_FORMAT_TO_MEDIA_TYPE = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
}


def build_upload_path(folder: str, filename: str) -> Path:
    return Path(config.upload_dir) / folder / filename


def get_image_media_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Unsupported logo type")


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

    filename = f"{uuid4()}{IMAGE_FORMAT_TO_EXTENSION[image_format]}"
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

    if image_format not in IMAGE_FORMAT_TO_EXTENSION:
        return None

    return image_format
