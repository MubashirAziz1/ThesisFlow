import logging
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.gateway.run_models import RunCreateRequest
from packages.harness.thesisflow.runtime.runs.manager import RunRecord
from packages.harness.thesisflow.utils.thread_id import ThreadId
from app.gateway.deps import get_run_manager, get_stream_bridge
from app.gateway.services import start_run, sse_consumer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads", tags=["runs"])

# Request Response Models
class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    assistant_id: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    multitask_strategy: str = "reject"
    created_at: str = ""
    updated_at: str = ""


def _record_to_response(record: RunRecord) -> RunResponse:
    """Map an in-memory run record onto the public run response."""

    return RunResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        assistant_id=record.assistant_id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("/{thread_id}/runs", response_model=RunResponse)
async def create_run(
    thread_id: ThreadId,
    body: RunCreateRequest,
    request: Request,
      ) -> RunResponse:
    """Create a background run (returns immediately)."""
    record = await start_run(
        body,
        thread_id,
        request,
        )
    return _record_to_response(record)


@router.post("/{thread_id}/runs/stream")
async def stream_run(
    thread_id: ThreadId,
    body: RunCreateRequest,
    request: Request,
) -> StreamingResponse:
    """Create a run and stream events via SSE. """

    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    record = await start_run(
        body,
        thread_id,
        request,
    )

    return StreamingResponse(
        sse_consumer(
            bridge,
            record,
            request,
            run_mgr,
        ),
        media_type="text/event-stream",
    )

@router.post("/{thread_id}/runs/wait", response_model=dict)
async def wait_run(
    thread_id: ThreadId,
    body: RunCreateRequest,
    request: Request,
) -> dict:
    """Create a run and block until it completes, returning the final state. """

    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    record = await start_run(
        body,
        thread_id,
        request,
    )

    # Reused/hydrated records have no local task. Wait on the bridge when this
    # worker can observe it; otherwise return durable status rather than
    # serializing whatever checkpoint happens to exist.
    if getattr(record, "store_only", False) and not getattr(bridge, "supports_cross_process", False):
        record = await _refresh_store_backed_run(run_mgr, record)
        return serialize_wait_run_status(record)

    if record.task is not None or getattr(record, "store_only", False):
        completed = await wait_for_run_completion(bridge, record, request, run_mgr)
    else:
        completed = True

    if completed:
        record = await _refresh_store_backed_run(run_mgr, record)
        if record.status == RunStatus.error:
            # A failure before the first checkpoint leaves an earlier answer at
            # the thread head. Return this run's error, never that old state.
            return serialize_wait_run_status(record)

    # Idempotent reuse is not bound to a run-specific checkpoint id. The latest
    # thread head may be a later run, so do not claim it as this run's result.
    if completed and not reused:
        try:
            accessor, config = await abuild_checkpoint_state_accessor(
                request,
                thread_id=thread_id,
                assistant_id=body.assistant_id,
            )
            snapshot = await accessor.aget(config)
            snapshot_config = snapshot.config or {}
            if snapshot_config.get("configurable", {}).get("checkpoint_id"):
                return serialize_channel_values_for_api(snapshot.values)
        except Exception:
            logger.exception("Failed to fetch final state for run %s", record.run_id)

    return serialize_wait_run_status(record)
