"""Async SQLAlchemy engine lifecycle management.

Initializes at Gateway startup, provides session factory for
repositories, disposes at shutdown.

"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from packages.harness.thesisflow.persistence.json_compat import dumps_json_safe
from packages.harness.thesisflow.utils.file_io import await_drained

# Recycle pooled Postgres connections before stale idle sockets can hang
# pool_pre_ping. The command timeout bounds stalled ORM queries independently.
POSTGRES_POOL_RECYCLE_SECONDS = 300
POSTGRES_COMMAND_TIMEOUT_SECONDS = 30


def _json_serializer(obj: object) -> str:
    """JSON serializer for every JSON column written through the ORM engine.

    ensure_ascii=False keeps Chinese character support; non-finite floats are
    normalized to ``None`` first — PostgreSQL jsonb rejects the bare
    ``NaN`` / ``Infinity`` token as invalid JSON, so a lenient dump turns a
    reachable non-finite value (caller metadata, model verdict JSON, provider
    usage numbers) into a ``DataError`` on the whole write.
    """
    return dumps_json_safe(obj)


def _postgres_engine_kwargs(
    *,
    echo: bool,
    pool_size: int,
    pool_recycle: int = POSTGRES_POOL_RECYCLE_SECONDS,
    command_timeout: float | None = POSTGRES_COMMAND_TIMEOUT_SECONDS,
    connect_args: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the shared SQLAlchemy engine options for PostgreSQL."""
    merged_connect_args = dict(connect_args or {})
    if command_timeout is not None:
        merged_connect_args["command_timeout"] = command_timeout
    return {
        "echo": echo,
        "pool_size": pool_size,
        "pool_pre_ping": True,
        "pool_recycle": pool_recycle,
        "connect_args": merged_connect_args,
        "json_serializer": _json_serializer,
    }


logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

_MISSING_DATABASE_SQLSTATE = "3D000"
_DUPLICATE_DATABASE_SQLSTATE = "42P04"


def _has_sqlstate(exc: BaseException, code: str) -> bool:
    """ Return whether *exc*, or anything it wraps, carries SQLSTATE *code*. """
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if getattr(current, "sqlstate", None) == code:
            return True
        for attr in ("orig", "__cause__", "__context__"):
            inner = getattr(current, attr, None)
            if isinstance(inner, BaseException):
                pending.append(inner)
    return False


def _is_missing_database_error(exc: BaseException) -> bool:
    """Return whether *exc* means the target PostgreSQL database is absent."""
    return _has_sqlstate(exc, _MISSING_DATABASE_SQLSTATE)


def _is_duplicate_database_error(exc: BaseException) -> bool:
    """Return whether *exc* means the target PostgreSQL database already exists."""
    return _has_sqlstate(exc, _DUPLICATE_DATABASE_SQLSTATE)


async def _auto_create_postgres_db(url: str) -> None:
    """Connect to the ``postgres`` maintenance DB and CREATE DATABASE.

    The target database name is extracted from *url*.  The connection is
    made to the default ``postgres`` database on the same server using
    ``AUTOCOMMIT`` isolation (CREATE DATABASE cannot run inside a
    transaction).
    """
    from sqlalchemy import text
    from sqlalchemy.engine.url import make_url

    parsed = make_url(url)
    db_name = parsed.database
    if not db_name:
        raise ValueError("Cannot auto-create database: no database name in URL")

    # Connect to the default 'postgres' database to issue CREATE DATABASE
    maint_url = parsed.set(database="postgres")
    maint_engine = create_async_engine(maint_url, isolation_level="AUTOCOMMIT")
    try:
        try:
            async with maint_engine.connect() as conn:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            logger.info("Auto-created PostgreSQL database: %s", db_name)
        except Exception as exc:
            # Two Gateways booting the same missing database both reach this point and
            # only one can win; for the loser the database exists and is usable, so the
            # caller's retry should proceed instead of the boot failing. Everything else
            # -- including "permission denied to create database" -- propagates
            # untouched, because a CREATE DATABASE failure is not a reason to mask the
            # bootstrap error that led here.
            if not _is_duplicate_database_error(exc):
                raise
            logger.info("PostgreSQL database %s was created by a peer process; continuing", db_name)
    finally:
        # Drain: the maintenance engine is local to this helper, so an
        # abandoned dispose leaves its pool to the ``postgres`` database with
        # nothing left to close it. Host cancellation must therefore be
        # delivered only after disposal actually finishes.
        await await_drained(maint_engine.dispose())


async def init_engine(
    backend: str,
    *,
    url: str = "",
    echo: bool = False,
    pool_size: int = 5,
    pool_recycle: int = POSTGRES_POOL_RECYCLE_SECONDS,
    command_timeout: float | None = POSTGRES_COMMAND_TIMEOUT_SECONDS,
    sqlite_dir: str = "",
    postgres_schema: str = "",
) -> None:
    """ Create the async engine and session factory, then auto-create tables. """
    global _engine, _session_factory

    if backend == "memory":
        logger.info("Persistence backend=memory -- ORM engine not initialized")
        return

    if backend == "postgres":
        try:
            import asyncpg  
        except ImportError:
            raise ImportError(
                "database.backend is set to 'postgres' but asyncpg is not installed.Please Install it "
            ) from None

        from deerflow.persistence.postgres_schema import build_asyncpg_connect_args

        pg_connect_args = build_asyncpg_connect_args(postgres_schema)
        _engine = create_async_engine(
            url,
            **_postgres_engine_kwargs(
                echo=echo,
                pool_size=pool_size,
                pool_recycle=pool_recycle,
                command_timeout=command_timeout,
                connect_args=pg_connect_args,
            ),
        )
    else:
        raise ValueError(f"Unknown persistence backend: {backend!r}")

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async def _ensure_postgres_schema() -> None:
        if backend == "postgres" and postgres_schema:
            from sqlalchemy.schema import CreateSchema

            async with _engine.begin() as conn:
                await conn.execute(CreateSchema(postgres_schema, if_not_exists=True))

    try:
        await _ensure_postgres_schema()
    except Exception as exc:
        if backend == "postgres" and _is_missing_database_error(exc):
            # Database not yet created -- attempt to auto-create it, then retry.
            await _auto_create_postgres_db(url)
            await await_drained(_engine.dispose())
            _engine = create_async_engine(
                url,
                **_postgres_engine_kwargs(
                    echo=echo,
                    pool_size=pool_size,
                    pool_recycle=pool_recycle,
                    command_timeout=command_timeout,
                    connect_args=pg_connect_args,
                ),
            )
            _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
            await _ensure_postgres_schema()
        else:
            raise

    logger.info("Persistence engine initialized: backend=%s", backend)


async def init_engine_from_config(config) -> None:
    """Convenience: init engine from a DatabaseConfig object."""
    if config.backend == "memory":
        await init_engine("memory")
        return
    await init_engine(
        backend=config.backend,
        url=config.app_sqlalchemy_url,
        echo=config.echo_sql,
        pool_size=config.pool_size,
        pool_recycle=config.pool_recycle,
        command_timeout=config.command_timeout,
        sqlite_dir=config.sqlite_dir if config.backend == "sqlite" else "",
        postgres_schema=config.postgres_schema if config.backend == "postgres" else "",
    )


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    """Return the async session factory, or None if backend=memory."""
    return _session_factory


def get_engine() -> AsyncEngine | None:
    """Return the async engine, or None if not initialized."""
    return _engine


async def close_engine() -> None:
    """Dispose the engine before releasing the process-global ownership."""
    global _engine, _session_factory

    engine = _engine
    if engine is None:
        _session_factory = None
        return

    async def dispose_and_clear() -> None:
        global _engine, _session_factory

        await engine.dispose()
        logger.info("Persistence engine closed")
        if _engine is engine:
            _engine = None
            _session_factory = None

    await await_drained(dispose_and_clear())