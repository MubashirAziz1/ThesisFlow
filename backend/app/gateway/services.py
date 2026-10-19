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
from typing import Any

from fastapi import HTTPException, Request

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.messages.utils import convert_to_messages

from app.gateway.run_models import RunCreateRequest
from packages.harness.thesisflow.utils.thread_id import validate_thread_id
from packages.harness.thesisflow.runtime.stream_modes import normalize_stream_modes
from packages.harness.thesisflow.runtime.runs.schemas import DisconnectMode
from packages.harness.thesisflow.runtime.runs.manager import RunRecord
from packages.harness.thesisflow.runtime.runs.worker import run_agent
from packages.harness.thesisflow.config import get_app_config
from app.gateway.deps import get_run_manager, get_run_context, get_stream_bridge
from packages.harness.thesisflow.runtime.stream_bridge import HEARTBEAT_SENTINEL, END_SENTINEL
logger = logging.getLogger(__name__)

_DEFAULT_ASSISTANT_ID = "lead_agent"
_DEFAULT_RECURSION_LIMIT = 100


def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """ Format a single SSE frame. """
    payload = json.dumps(data, default=str, ensure_ascii=False)
    parts = [f"event: {event}", f"data: {payload}"]
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


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


def build_run_config(thread_id: str, request_config: dict[str, Any] | None,) -> dict[str, Any]:
    """ Build the LangGraph RunnableConfig for a run.

    ``configurable`` is seeded from the ``lead-agent:`` section of
    config.yaml (read through :class:`AppConfig`): the default model name,
    that model's configured parameters, and plan mode. Request-level
    ``configurable`` values override the config.yaml defaults, and
    ``thread_id`` is always forced to the run's thread.
    """

    config: dict[str, Any] = {"recursion_limit": _DEFAULT_RECURSION_LIMIT}

    configurable: dict[str, Any] = {}

    app_config = get_app_config()
    if app_config.lead_agent:
        lead_agent = app_config.lead_agent
        configurable["model_name"] = lead_agent.model_name
        configurable["is_plan_mode"] = lead_agent.is_plan_mode

    if request_config:
        configurable.update(request_config.get("configurable") or {})

    configurable["thread_id"] = thread_id
    config["configurable"] = configurable

    return config

def resolve_agent_factory(assistant_id: str | None):
    """ Resolve the agent factory callable from config. """
    
    from packages.harness.thesisflow.agents.lead_agent.agent import assemble_lead_agent

    return assemble_lead_agent

async def start_run(
    body: RunCreateRequest,
    thread_id: str,
    request: Request
) -> RunRecord:
    """ Create a RunRecord and launch the background agent task. """

    try:
        validate_thread_id(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    

    stream_modes = normalize_stream_modes(body.stream_mode)
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request) 
    run_ctx = get_run_context(request)

    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    app_config = get_app_config()
    model_name = app_config.lead_agent.model_name
    if model_name:
        resolved = app_config.get_model_config(model_name)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"Model {model_name!r} is not in the configured model allowlist",
            )
  
    config = build_run_config(thread_id, body.config)
    agent_factory = resolve_agent_factory(body.assistant_id)
    graph_input = normalize_input(body.input)

    async def agent_worker(record: RunRecord) -> None:

        await run_agent(
                bridge,
                run_mgr,
                record,
                ctx=run_ctx,    
                agent_factory=agent_factory,
                graph_input=graph_input,
                config=config,
                )

    try:
        record = await run_mgr.create_or_reject(
                thread_id,
                body.assistant_id,
                on_disconnect=disconnect,
                model_name=model_name,
            )
        worker = agent_worker(record)

        try:
            record.task = asyncio.create_task(worker)
        except Exception as exc:
            worker.close()
            raise

    except Exception as exc:
        raise

    return record   


async def sse_consumer(
    bridge: StreamBridge,
    record: RunRecord,
    request: Request,
    run_mgr: RunManager,
    *,
    apply_on_disconnect: bool = True,
):
    """ Async generator that yields SSE frames from the bridge. """
    last_event_id = request.headers.get("Last-Event-ID")

    terminal_emitted = False
    disconnect_observed = False
    try:
        async for entry in bridge.subscribe(record.run_id, last_event_id=last_event_id):
            if await request.is_disconnected():
                disconnect_observed = True
                break

            if entry is HEARTBEAT_SENTINEL:
                yield ": heartbeat\n\n"
                continue

            if entry is END_SENTINEL:
                terminal_emitted = True
                yield format_sse("end", None, event_id=entry.id or None)
                return

            yield format_sse(entry.event, entry.data, event_id=entry.id or None)

        if not disconnect_observed:
            raise RuntimeError("stream bridge subscription ended before a terminal event")
    except (GeneratorExit, asyncio.CancelledError):
        disconnect_observed = True
        raise
