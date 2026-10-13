"""Configuration for stream bridge."""

from typing import Literal

StreamBridgeType = Literal["memory", "redis"]
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0
MAX_HEARTBEAT_INTERVAL_SECONDS = 86_400.0
MAX_RECOVERED_STREAM_CLEANUP_DELAY_SECONDS = 86_400.0
