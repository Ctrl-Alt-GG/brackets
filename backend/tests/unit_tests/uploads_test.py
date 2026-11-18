import asyncio
import struct
import threading
import zlib
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from bracket.config import config
from bracket.utils import uploads
from bracket.utils.uploads import normalize_image


def compressed_png(width: int, height: int) -> bytes:
    """A real RGB PNG made a row at a time, without allocating its expanded bitmap."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
        )

    compressor = zlib.compressobj()
    row = bytes(1 + width * 3)
    pixels = b"".join(compressor.compress(row) for _ in range(height)) + compressor.flush()
    header = struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize(
    ("width", "height"), [(8000, 8000), (5000, 1), (12000, 8000), (20000, 10000)]
)
def test_compressed_logos_are_bounded_before_bitmap_decoding(width: int, height: int) -> None:
    content = compressed_png(width, height)
    assert len(content) < config.upload_max_bytes

    with patch("bracket.utils.uploads.ImageOps.exif_transpose") as decode:
        with pytest.raises(HTTPException) as rejected:
            normalize_image(content)
        decode.assert_not_called()

    assert rejected.value.status_code == 400
    assert "4 megapixels" in rejected.value.detail


def test_normalized_logo_is_resized_and_drops_metadata() -> None:
    image = Image.new("RGB", (1000, 500))
    exif = Image.Exif()
    exif[0x010E] = "private camera metadata"
    source = BytesIO()
    image.save(source, format="PNG", exif=exif)

    normalized = normalize_image(source.getvalue())
    assert normalized is not None
    with Image.open(BytesIO(normalized[1])) as stored:
        assert stored.size == (512, 256)
        assert not stored.getexif()


@pytest.mark.asyncio
async def test_images_are_processed_outside_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The event loop answers other requests while an upload is decoded and encoded."""
    processing, finish = threading.Event(), threading.Event()

    def slow_normalize(content: bytes) -> tuple[str, bytes]:
        processing.set()
        # Only the event loop can let this finish.
        if not finish.wait(timeout=5):
            raise TimeoutError("the event loop was blocked while the image was processed")
        return "PNG", content

    monkeypatch.setattr(uploads, "normalize_image", slow_normalize)
    session = SimpleNamespace(info={})
    stored = asyncio.create_task(
        uploads.store_validated_image_upload(
            UploadFile(BytesIO(b"an image"), filename="logo.png"),
            uploads.UploadFolder.TEAM_LOGOS,
            session,  # type: ignore[arg-type]
        )
    )
    await asyncio.to_thread(processing.wait, 5)
    finish.set()
    upload = await stored
    assert session.info[uploads.NEW_UPLOADS] == [upload]
    upload.path.unlink()
