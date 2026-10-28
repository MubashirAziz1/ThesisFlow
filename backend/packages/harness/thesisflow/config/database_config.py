"""
Unified database backend configuration.

Controls BOTH the LangGraph checkpointer and the DeerFlow application
persistence layer (runs, threads metadata, users, etc.). The user
configures one backend; the system handles physical separation details.

"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from .postgres_schema import POSTGRES_SCHEMA_PATTERN, validate_postgres_schema

logger = logging.getLogger(__name__)


def resolve_checkpoint_graph_cache_max(database_config: Any, field_name: str, default: int) -> int:
    """Read a graph-cache cap from a database config-ish object.

    Tolerates stub configs (SimpleNamespace/MagicMock in tests, missing
    section): anything that is not a plain int >= 1 falls back to
    ``default``.
    """
    section = getattr(database_config, "checkpoint_graph_cache", None)
    value = getattr(section, field_name, None)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return value


CheckpointChannelMode = Literal["full", "delta"]
DEFAULT_CHECKPOINT_SNAPSHOT_FREQUENCY = 10

class CheckpointDeltaConfig(BaseModel):
    """Tuning knobs for ``checkpoint_channel_mode: delta``. """

    snapshot_frequency: int = Field(
        default=DEFAULT_CHECKPOINT_SNAPSHOT_FREQUENCY,
        ge=1,
        description=(
            "DeltaChannel snapshot cadence: a full messages snapshot is stored "
            "every N per-step writes (higher = smaller checkpoints, slower "
            "materialization). Restart is required, and all processes sharing "
            "one checkpoint database must use the same value."
        ),
    )

class DatabaseConfig(BaseModel):
    backend: Literal["memory", "postgres"] = Field(
        default="memory",
        description=("Storage backend for both checkpointer and application data. 'memory' for development (no persistence across restarts), 'postgres' for production multi-node deployment."),
    )
    checkpoint_channel_mode: CheckpointChannelMode = Field(
        default="full",
        description=(
            "Checkpoint representation for accumulating channels. "
            "'full' preserves full-value message checkpoints; 'delta' uses "
            "LangGraph DeltaChannel for messages. Restart is required, and all "
            "processes sharing one checkpoint database must use the same value."
        ),
    )

    checkpoint_delta: CheckpointDeltaConfig = Field(
        default_factory=CheckpointDeltaConfig,
        description="Delta-mode checkpoint tuning. Only applies when checkpoint_channel_mode is 'delta'.",
    )
    
    postgres_url: str = Field(
        default="",
        description=(
            "PostgreSQL connection URL, shared by checkpointer and app. "
            "Use $DATABASE_URL in config.yaml to reference .env. "
            "Example: postgresql://user:pass@host:5432/deerflow "
            "(the +asyncpg driver suffix is added automatically where needed)."
        ),
    )
    echo_sql: bool = Field(
        default=False,
        description="Echo all SQL statements to log (debug only).",
    )
    pool_size: int = Field(
        default=5,
        gt=0,
        description="Connection pool size for the app ORM engine (postgres only).",
    )
    pool_recycle: int = Field(
        default=300,
        gt=0,
        description="Seconds before app ORM PostgreSQL connections are recycled.",
    )
    command_timeout: float | None = Field(
        default=30,
        gt=0,
        allow_inf_nan=False,
        description="Timeout in seconds for app ORM PostgreSQL commands. Set to null to disable the command timeout.",
    )
    postgres_schema: str = Field(
        default="",
        description=(
            "PostgreSQL schema for both app ORM tables and LangGraph "
            "checkpointer/store tables (postgres only). Empty string keeps "
            "the server default search_path (usually 'public'). When set, "
            "the schema is created automatically at startup and applied via "
            "connection-level search_path. Only plain identifiers are "
            f"allowed: {POSTGRES_SCHEMA_PATTERN}."
        ),
    )

    @field_validator("postgres_schema")
    @classmethod
    def _validate_postgres_schema(cls, value: str) -> str:
        return validate_postgres_schema(value)

    @property
    def app_sqlalchemy_url(self) -> str:
        """SQLAlchemy async URL for the application ORM engine."""
        if self.backend == "postgres":
            url = self.postgres_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgres://"):
                # libpq's short alias: accepted by the psycopg checkpointer, but not a SQLAlchemy dialect.
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            return url
        raise ValueError(f"No SQLAlchemy URL for backend={self.backend!r}")

    @property
    def app_sync_sqlalchemy_url(self) -> str:
        """ SQLAlchemy *synchronous* URL for the application ORM data. """

        if self.backend == "postgres":
            url = self.postgres_url
            if self.postgres_schema:
                # The synchronous agent stores use psycopg via SQLAlchemy,
                # so they need the same search_path as the async ORM engine
                # and LangGraph stores.
                from ..persistence.postgres_schema import dsn_with_search_path

                url = dsn_with_search_path(url, self.postgres_schema)
            if url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            elif url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            return url
        raise ValueError(f"No SQLAlchemy URL for backend={self.backend!r}")