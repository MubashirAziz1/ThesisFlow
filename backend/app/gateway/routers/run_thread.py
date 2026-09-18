import json
import logging
import time
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.gateway.run_models import RunCreateRequest
from packages.harness.thesisflow.utils.thread_id import ThreadId

# region agent log
with open(r"D:\AI\research_assistant\debug-983b7e.log", "a", encoding="utf-8") as _debug_file:
    _debug_file.write(json.dumps({"sessionId": "983b7e", "runId": "pre-fix", "hypothesisId": "H1,H2", "location": "app/gateway/routers/run_thread.py:imports", "message": "Router dependencies imported", "data": {"threadIdModule": ThreadId.__module__, "requestModelModule": RunCreateRequest.__module__}, "timestamp": int(time.time() * 1000)}) + "\n")
# endregion

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


