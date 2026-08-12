import asyncio
from collections.abc import Awaitable, Callable

from heliclockter import timedelta

from bracket.utils.asyncio import AsyncioTasksManager
from bracket.utils.logging import logger

CronjobT = Callable[[], Awaitable[None]]


async def run_cronjob(cronjob_entrypoint: CronjobT, delta_time: timedelta) -> None:
    while True:
        await asyncio.sleep(delta_time.total_seconds())

        try:
            await cronjob_entrypoint()
        except Exception as e:
            logger.exception(f"Could not run cronjob {cronjob_entrypoint.__name__}: {e}")


CRONJOBS: tuple[tuple[timedelta, CronjobT], ...] = ()


def start_cronjobs() -> None:
    for delta_time, cronjob_entrypoint in CRONJOBS:
        AsyncioTasksManager.add_coroutine(run_cronjob(cronjob_entrypoint, delta_time))
