"""Run lifecycle service layer.

Centralizes the business logic for creating runs, formatting SSE
frames, and consuming stream bridge events. 
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from typing import Any
import re

from fastapi import HTTPException, Request

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.messages.utils import convert_to_messages

from app.gateway.run_models import RunCreateRequest
from packages.harness.thesisflow.utils.thread_id import validate_thread_id
from packages.harness.thesisflow.runtime.stream_modes import normalize_stream_modes
from packages.harness.thesisflow.runtime.runs.schemas import DisconnectMode
from packages.harness.thesisflow.runtime.runs.manager import RunRecord


logger = logging.getLogger(_name__)

_DEFAULT_ASSISTANT_ID = "lead_agent"


def normalize_input(raw_input: dict[str, Any] | None) -> dict[str, Any]:
    """ Convert LangGraph Platform input format to LangChain state dict. """

    if raw_input is None:
        return {}
    result = raw_input
    messages = raw_input.get("messages")
    if messages and isinstance(messages, list):
        converted: list[Any] = []
        for index, msg in enumerate(messages):
            if isinstance(msg, BaseMessage):
                converted.append(msg)
            elif isinstance(msg, dict):
                try:
                    converted.extend(convert_to_messages([msg]))
                except (ValueError, TypeError, NotImplementedError) as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid message at input.messages[{index}]: {exc}",
                    ) from exc
            else:
                converted.append(msg)
        result = {**raw_input, "messages": converted}

    return result


def build_run_config(thread_id: str, *, assistant_id: str | None = None) -> dict[str, Any]:
    
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    if assistant_id and assistant_id != _DEFAULT_ASSISTANT_ID:
        normalized = assistant_id.strip().lower().replace("_", "-")
        if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
            raise ValueError(f"Invalid assistant_id {assistant_id!r}: must contain only letters, digits, and hyphens after normalization.")

        config["configurable"]["agent_name"] = normalized

    return config


async def start_run(
    body: RunCreateRequest,
    thread_id: str,
) -> RunRecord:
    """ Create a RunRecord and launch the background agent task. """

    try:
        validate_thread_id(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    

    stream_modes = normalize_stream_modes(body.stream_mode)
    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    try:
        agent_factory = resolve_agent_factory(body.assistant_id)
        graph_input = normalize_input(body.input)
        config = build_run_config(thread_id, assistant_id=body.assistant_id)
        agent_config = None
        await run_agent(    
                agent_factory=agent_factory,
                graph_input=graph_input,
                config=config,
                stream_modes=stream_modes,
                stream_subgraphs=body.stream_subgraphs,
                interrupt_before=body.interrupt_before,
                interrupt_after=body.interrupt_after,
                )
    
    finally:
        if owner_context_token is not None:
            reset_current_user(owner_context_token)
