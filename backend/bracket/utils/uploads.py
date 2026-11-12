from __future__ import annotations

import mimetypes
import warnings
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import aiofiles
import aiofiles.os
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from bracket.config import config

# Pillow registers formats lazily; this loads the common ones, including PNG and JPEG.
Image.preinit()
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


async def remove_existing_uploads(folder: str, filenames: list[str | None]) -> None:
    for filename in filenames:
        await remove_existing_upload(folder, filename)


async def store_validated_image_upload(file: UploadFile, folder: str) -> str:
    content = await file.read(config.upload_max_bytes + 1)
    if len(content) > config.upload_max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Uploaded file exceeds the {config.upload_max_bytes}-byte limit",
        )

    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")

    normalized = normalize_image(content)
    if normalized is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only PNG and JPEG image uploads are supported",
        )

    image_format, image_content = normalized
    filename = f"{uuid4()}{mimetypes.guess_extension(Image.MIME[image_format])}"
    upload_path = build_upload_path(folder, filename)
    await aiofiles.os.makedirs(str(upload_path.parent), exist_ok=True)
    async with aiofiles.open(upload_path, "wb") as file_handle:
        await file_handle.write(image_content)
    return filename


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
        with (
            warnings.catch_warnings(action="error", category=Image.DecompressionBombWarning),
            Image.open(BytesIO(content)) as image,
        ):
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
