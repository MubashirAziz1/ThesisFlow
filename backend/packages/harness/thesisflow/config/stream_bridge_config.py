"""Configuration for stream bridge."""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from deerflow.config._boolean_guards import reject_boolean

StreamBridgeType = Literal["memory", "redis"]
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0
MAX_HEARTBEAT_INTERVAL_SECONDS = 86_400.0
MAX_RECOVERED_STREAM_CLEANUP_DELAY_SECONDS = 86_400.0


class StreamBridgeConfig(BaseModel):
    """Configuration for the stream bridge that connects agent workers to SSE endpoints."""

    type: StreamBridgeType = Field(
        default="memory",
        description="Stream bridge backend type. 'memory' uses an in-process event log (single-process only). 'redis' uses Redis Streams for multi-worker Docker deployments.",
    )
    
    queue_maxsize: int = Field(
        default=256,
        ge=1,
        description="Maximum number of events retained per run (memory bridge queue size).",
    )
    heartbeat_interval_seconds: float = Field(
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        gt=0,
        le=MAX_HEARTBEAT_INTERVAL_SECONDS,
        allow_inf_nan=False,
        description=("Idle seconds between stream heartbeats (maximum 86400). Applies to SSE clients, non-streaming wait requests, and internal stream subscribers."),
    )
    recovered_stream_cleanup_delay_seconds: float = Field(
        default=60.0,
        ge=0,
        le=MAX_RECOVERED_STREAM_CLEANUP_DELAY_SECONDS,
        allow_inf_nan=False,
        description=(
            "Seconds to wait after publishing an END marker for a recovered orphaned run before deleting the stream key (maximum 86400). Gives reconnecting SSE clients time to drain the end signal. Only applies to the redis bridge."
        ),
    )


# Global configuration instance — None means no stream bridge is configured
# (falls back to memory with defaults).
_stream_bridge_config: StreamBridgeConfig | None = None


def get_stream_bridge_config() -> StreamBridgeConfig | None:
    """Get the current stream bridge configuration, or None if not configured."""
    return _stream_bridge_config

