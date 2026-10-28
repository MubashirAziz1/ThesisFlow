"""Centralized accessors for singleton objects stored on ``app.state``. """


from __future__ import annotations

from typing import TypeVar, cast

T = TypeVar("T")
from collections.abc import Callable
from fastapi import HTTPException, Request
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, AsyncExitStack
from fastapi import FastAPI

from packages.harness.thesisflow.runtime.runs.manager import RunManager
from packages.harness.thesisflow.runtime.stream_bridge import StreamBridge
from packages.harness.thesisflow.config.app_config import AppConfig, get_app_config
from packages.harness.thesisflow.runtime.runs.worker import RunContext
from packages.harness.thesisflow.runtime.stream_bridge.async_provider import make_stream_bridge
from packages.harness.thesisflow.runtime.checkpoint_mode import freeze_checkpoint_channel_mode, freeze_checkpoint_snapshot_frequency


@asynccontextmanager
async def langgraph_runtime(app: FastAPI, startup_config: AppConfig) -> AsyncGenerator[None, None]:
    """ Bootstrap and tear down all LangGraph runtime singletons. """

    from packages.harness.thesisflow.runtime.checkpointer.async_provider import make_checkpointer

    async with AsyncExitStack() as stack:
        config = startup_config
        app.state.checkpoint_channel_mode = freeze_checkpoint_channel_mode(config.database.checkpoint_channel_mode)
        app.state.checkpoint_snapshot_frequency = freeze_checkpoint_snapshot_frequency(config.database.checkpoint_delta.snapshot_frequency)

        app.state.stream_bridge = await stack.enter_async_context(make_stream_bridge(config))
        app.state.checkpointer = await stack.enter_async_context(make_checkpointer(config))
        app.state.app_config = config
        app.state.run_manager = RunManager()

        await app.state.run_manager.start_heartbeat()

        try:
            yield
        finally:
            run_manager = getattr(app.state, "run_manager", None)
            if run_manager is not None:
                await run_manager.shutdown()



def _require(attr: str, label: str) -> Callable[[Request], T]:
    """Create a FastAPI dependency that returns ``app.state.<attr>`` or 503."""

    def dep(request: Request) -> T:
        val = getattr(request.app.state, attr, None)
        if val is None:
            raise HTTPException(status_code=503, detail=f"{label} not available")
        return cast(T, val)

    dep.__name__ = dep.__qualname__ = f"get_{attr}"
    return dep


get_run_manager: Callable[[Request], RunManager] = _require("run_manager", "Run manager")
get_stream_bridge: Callable[[Request], StreamBridge] = _require("stream_bridge", "Stream bridge")


def get_run_context(request: Request) -> RunContext:
    """ Build a :class:`RunContext` from ``app.state`` singletons. """

    return RunContext(
        checkpointer = get_checkpojter(request),
        checkpoint_channel_mode=getattr(request.app.state, "checkpoint_channel_mode", "full"),
        checkpoint_snapshot_frequency=getattr(request.app.state, "checkpoint_snapshot_frequency", None),
        app_config=get_app_config())