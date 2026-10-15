""" Async stream bridge factory. """

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import AsyncIterator

from packages.harness.thesisflow.config.app_config import AppConfig
from packages.harness.thesisflow.config.stream_bridge_config import StreamBridgeConfig, get_stream_bridge_config
from packages.harness.thesisflow.utils.file_io import await_drained

from .base import DEFAULT_HEARTBEAT_INTERVAL_SECONDS, StreamBridge

logger = logging.getLogger(__name__)



def _resolve_config(app_config: AppConfig | None) -> StreamBridgeConfig | None:
    if app_config is None:
        config = get_stream_bridge_config()
    else:
        config = app_config.stream_bridge

    return config


@contextlib.asynccontextmanager
async def make_stream_bridge(app_config: AppConfig | None = None) -> AsyncIterator[StreamBridge]:
    """ Async context manager that yields a :class:`StreamBridge`. """
    
    config = _resolve_config(app_config)

    if config is None or config.type == "memory":
        from deerflow.runtime.stream_bridge.memory import MemoryStreamBridge

        maxsize = config.queue_maxsize if config is not None else 256
        heartbeat_interval = config.heartbeat_interval_seconds if config is not None else DEFAULT_HEARTBEAT_INTERVAL_SECONDS
        bridge = MemoryStreamBridge(
            queue_maxsize=maxsize,
            heartbeat_interval=heartbeat_interval,
        )
        logger.info(
            "Stream bridge initialised: memory (queue_maxsize=%d, heartbeat_interval_seconds=%.1f)",
            maxsize,
            heartbeat_interval,
        )
        try:
            yield bridge
        finally:
            await await_drained(bridge.close())
        return

    raise ValueError(f"Unknown stream bridge type: {config.type!r}")