""" Async checkpointer factory. """

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from langgraph.types import Checkpointer

from packages.harness.thesisflow.config.app_config import AppConfig, get_app_config
from packages.harness.thesisflow.persistence.postgres_schema import create_schema_sql, dsn_with_search_path

logger = logging.getLogger(__name__)

@contextlib.asynccontextmanager
async def _async_checkpointer(config) -> AsyncIterator[Checkpointer]:
    """Async context manager that constructs and tears down a checkpointer."""

    if config.type == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()
        return

    # TODO: Implement postgres checkpointer for production
    # if config.type == "postgres":
    #     if not config.connection_string:
    #         raise ValueError(POSTGRES_CONN_REQUIRED)

    #     AsyncPostgresSaver, _ = _ensure_postgres_imports()
    #     pool = _build_postgres_pool(config.connection_string, config.postgres_schema)
    #     async with drained_async_context(pool):
    #         await _ensure_postgres_schema_with_pool(pool, config.postgres_schema)
    #         saver = AsyncPostgresSaver(conn=pool)
    #         await saver.setup()
    #         yield saver
    #     return

    raise ValueError(f"Unknown checkpointer type: {config.type!r}")


@contextlib.asynccontextmanager
async def _select_inner_checkpointer(app_config: AppConfig) -> AsyncIterator[Checkpointer]:
    """Yield the raw checkpointer selected by *app_config* (no delta-cache wrapping).

    Priority:
    1. Legacy ``checkpointer:`` config section (backward compatible)
    2. Default InMemorySaver
    """
    
    if app_config.checkpointer is not None:
        async with _async_checkpointer(app_config.checkpointer) as saver:
            yield saver
            return

    # Default: in-memory
    from langgraph.checkpoint.memory import InMemorySaver

    yield InMemorySaver()


@contextlib.asynccontextmanager
async def make_checkpointer(app_config: AppConfig | None = None) -> AsyncIterator[Checkpointer]:
    """ Async context manager that yields a checkpointer for the caller's lifetime. """
    from packages.harness.thesisflow.runtime.checkpoint_mode import frozen_checkpoint_channel_mode

    if app_config is None:
        app_config = get_app_config()

    async with _select_inner_checkpointer(app_config) as saver:
        db_config = getattr(app_config, "database", None)
        mode = frozen_checkpoint_channel_mode() or (db_config.checkpoint_channel_mode if db_config is not None else "full")

        yield saver