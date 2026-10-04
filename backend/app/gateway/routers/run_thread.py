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


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads", tags=["runs"])

# Request Response Models
class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    assistant_id: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
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


