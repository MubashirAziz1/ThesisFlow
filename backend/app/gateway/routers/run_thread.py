import logging
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

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
    idempotency_key: IdempotencyKeyHeader = None,
) -> StreamingResponse:
    """Create a run and stream events via SSE.

    The response includes a ``Content-Location`` header with the run's
    resource URL, matching the LangGraph Platform protocol.  The
    ``useStream`` React hook uses this to extract run metadata.
    """
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    record = await start_run(
        body,
        thread_id,
        request,
        idempotency_key=_scope_http_run_idempotency_key(request, thread_id, idempotency_key),
    )

    # Same shape join already rejects: a reused store-only handle on a
    # process-local bridge has no owner stream. Subscribing would create an
    # empty log and wait forever. Terminal reuse still goes through
    # sse_consumer with emit_gap_on_missing_stream so a missing stream emits
    # gap rather than a bare end. First-time creates keep the default `end`.
    if record.store_only and not bridge.supports_cross_process and record.status in (RunStatus.pending, RunStatus.running):
        raise HTTPException(
            status_code=409,
            detail=f"Run {record.run_id} is not active on this worker and cannot be streamed",
        )

    return StreamingResponse(
        sse_consumer(
            bridge,
            record,
            request,
            run_mgr,
            emit_gap_on_missing_stream=record.idempotency_reused,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            # LangGraph Platform includes run metadata in this header.
            # The SDK uses a greedy regex to extract the run id from this path,
            # so it must point at the canonical run resource without extra suffixes.
            "Content-Location": f"/api/threads/{thread_id}/runs/{record.run_id}",
        },
    )
