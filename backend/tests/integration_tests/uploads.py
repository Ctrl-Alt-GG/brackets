import asyncio
from pathlib import Path

import aiofiles.os


async def wait_until_removed(path: Path) -> None:
    """Replaced uploads are removed by a background task, which runs after the response is sent."""
    for _ in range(50):
        if not await aiofiles.os.path.exists(path):
            return
        await asyncio.sleep(0.02)

    raise AssertionError(f"{path} was not removed")
