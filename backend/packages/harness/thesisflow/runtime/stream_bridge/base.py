"""Abstract stream bridge protocol.

StreamBridge decouples agent workers (producers) from SSE endpoints
(consumers), aligning with LangGraph Platform's Queue + StreamManager
architecture.
"""

from __future__ import annotations

import abc
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from packages.harness.thesisflow.config.stream_bridge_config import DEFAULT_HEARTBEAT_INTERVAL_SECONDS, MAX_HEARTBEAT_INTERVAL_SECONDS


@dataclass(frozen=True)
class StreamEvent:
    """ Single stream event. """

    id: str
    event: str
    data: Any


HEARTBEAT_SENTINEL = StreamEvent(id="", event="__heartbeat__", data=None)
END_SENTINEL = StreamEvent(id="", event="__end__", data=None)
type StreamItem = StreamEvent


class StreamBridge(abc.ABC):
    """Abstract base for stream bridges."""

    supports_cross_process: bool = False

    def __init__(self, *, heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS) -> None:
        self._heartbeat_interval = heartbeat_interval

    @property
    def heartbeat_interval(self) -> float:
        """Default number of idle seconds between subscriber heartbeats."""
        return self._heartbeat_interval


    @abc.abstractmethod
    async def publish(self, run_id: str, event: str, data: Any) -> None:
        """Enqueue a single event for *run_id* (producer side)."""


    @abc.abstractmethod
    async def publish_end(self, run_id: str) -> None:
        """Signal that no more events will be produced for *run_id*."""


    @abc.abstractmethod
    def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float | None = None,
    ) -> AsyncIterator[StreamItem]:
        """ Async iterator that yields events for *run_id* (consumer side). """


    @abc.abstractmethod
    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        """ Release resources associated with *run_id*. """


    async def ping(self) -> bool:
        """ Return whether the bridge's external backend is reachable right now. """
        return True


    async def close(self) -> None:
        """Release backend resources.  Default is a no-op."""