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
from packages.harness.thesisflow.config.app_config import AppConfig


@asynccontextmanager
async def langgraph_runtime(app: FastAPI, startup_config: AppConfig) -> AsyncGenerator[None, None]:
    """Bootstrap and tear down all LangGraph runtime singletons.

    ``startup_config`` is the snapshot taken once during lifespan startup.
    In-flight runs are drained before the exit stack releases anything
    entered above this yield.
    """

    if startup_config is None:
        raise RuntimeError("langgraph_runtime() requires a startup AppConfig")

    async with AsyncExitStack() as stack:
        config = startup_config
        app.state.app_config = config
        app.state.run_manager = RunManager()

        async def _release_runtime_state() -> None:
            app.state.run_manager = None
            app.state.app_config = None

        # Unwinds after the finally drain, before any earlier stack resources close.
        stack.push_async_callback(_release_runtime_state)

        try:
            # Start the lease heartbeat if enabled (multi-worker deployments).
            await app.state.run_manager.start_heartbeat()
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