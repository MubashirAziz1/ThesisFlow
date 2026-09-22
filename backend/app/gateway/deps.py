"""Centralized accessors for singleton objects stored on ``app.state``. """


from __future__ import annotations

from typing import cast
from collections.abc import Callable
from fastapi import HTTPException, Request

from packages.harness.thesisflow.runtime import RunManager

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