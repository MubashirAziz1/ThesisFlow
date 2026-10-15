"""Dedicated async offload helper for filesystem work."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

async def await_drained[T](coro: Coroutine[Any, Any, T]) -> T:
    """ Await *coro* to completion even when the caller is cancelled meanwhile. """
    task = asyncio.ensure_future(coro)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Drain: the shielded inner task keeps running; absorb repeated
        # cancellation until it finishes, then let the cancellation through.
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            task.exception()
        raise