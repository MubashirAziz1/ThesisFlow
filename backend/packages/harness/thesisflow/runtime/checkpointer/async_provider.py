""" Async checkpointer factory. """

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from langgraph.types import Checkpointer

from packages.harness.thesisflow.config.app_config import AppConfig, get_app_config
from packages.harness.thesisflow.persistence.postgres_schema import create_schema_sql, dsn_with_search_path
from packages.harness.thesisflow.runtime.cancellation import drained_async_context

logger = logging.getLogger(__name__)

POSTGRES_INSTALL = (
    "langgraph-checkpoint-postgres is required for the PostgreSQL checkpointer. Install the package extra with: pip install 'deerflow-harness[postgres]' (or use: uv sync --all-packages --extra postgres when developing locally)"
)

def _ensure_postgres_imports():
    """Import and return (AsyncPostgresSaver, AsyncConnectionPool), raising ImportError on failure."""
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:
        raise ImportError(POSTGRES_INSTALL) from exc

    try:
        from psycopg_pool import AsyncConnectionPool
    except ImportError as exc:
        raise ImportError(POSTGRES_INSTALL) from exc

    return AsyncPostgresSaver, AsyncConnectionPool

async def _ensure_postgres_schema_with_pool(pool, schema: str) -> None:
    """Create the configured schema before LangGraph creates its tables."""
    statement = create_schema_sql(schema)
    if statement is None:
        return
   
    async with drained_async_context(pool.connection()) as conn:
        await conn.execute(statement)

def _build_postgres_pool(conn_string: str, schema: str = ""):
    """Build an AsyncConnectionPool with TCP keepalive and connection checking."""
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 6,
    }
   
    dsn = dsn_with_search_path(conn_string, schema)

    return AsyncConnectionPool(
        dsn,
        kwargs=kwargs,
        check=AsyncConnectionPool.check_connection,
    )

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
async def _async_checkpointer_from_database(db_config) -> AsyncIterator[Checkpointer]:
    """Async context manager that constructs a checkpointer from unified DatabaseConfig."""

    if db_config.backend == "postgres":
        if not db_config.postgres_url:
            raise ValueError("database.postgres_url is required for the postgres backend")

        AsyncPostgresSaver, _ = _ensure_postgres_imports()
        pool = _build_postgres_pool(db_config.postgres_url, db_config.postgres_schema)
        async with drained_async_context(pool):
            await _ensure_postgres_schema_with_pool(pool, db_config.postgres_schema)
            saver = AsyncPostgresSaver(conn=pool)
            await saver.setup()
            yield saver
        return

    raise ValueError(f"Unknown database backend: {db_config.backend!r}")


@contextlib.asynccontextmanager
async def _select_inner_checkpointer(app_config: AppConfig) -> AsyncIterator[Checkpointer]:
    """Yield the raw checkpointer selected by *app_config* (no delta-cache wrapping).

    Priority:
    1. Unified ``database:`` config section
    2. Default InMemorySaver
    """

    # Unified database config
    db_config = getattr(app_config, "database", None)
    if db_config is not None and db_config.backend != "memory":
        async with _async_checkpointer_from_database(db_config) as saver:
            yield saver
            return

    # Default: in-memory
    from langgraph.checkpoint.memory import InMemorySaver

    yield InMemorySaver()


@contextlib.asynccontextmanager
async def make_checkpointer(app_config: AppConfig | None = None) -> AsyncIterator[Checkpointer]:
    """ Async context manager that yields a checkpointer for the caller's lifetime. 
    Yields an ``InMemorySaver`` when no checkpointer is configured in *config.yaml*.
    """
    
    from packages.harness.thesisflow.runtime.checkpoint_mode import frozen_checkpoint_channel_mode


    if app_config is None:
        app_config = get_app_config()

    async with _select_inner_checkpointer(app_config) as saver:
        db_config = getattr(app_config, "database", None)
        mode = frozen_checkpoint_channel_mode() or (db_config.checkpoint_channel_mode if db_config is not None else "full")

        yield saver