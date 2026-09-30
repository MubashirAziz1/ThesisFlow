"""Shared request models for the LangGraph-compatible run boundary."""

from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from packages.harness.thesisflow.run_time.stream_modes import RunStreamMode

class RunCreateRequest(BaseModel):
    """Validated run request used by both HTTP and internal launch paths."""

    model_config = ConfigDict(extra="forbid")

    assistant_id: str | None = Field(default=None, description="Agent / assistant to use")
    input: dict[str, Any] | None = Field(default=None, description="Graph input (e.g. {messages: [...]})")
    config: dict[str, Any] | None = Field(default=None, description="RunnableConfig overrides")
    checkpoint_id: str | None = Field(default=None, description="Resume from checkpoint")
    checkpoint: dict[str, Any] | None = Field(default=None, description="Full checkpoint object")
    stream_mode: list[RunStreamMode] | RunStreamMode | None = Field(default=None, description="Supported stream mode(s)")
    