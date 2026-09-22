"""In-memory run registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .schemas import DisconnectMode, RunStatus

logger = logging.getLogger(__name__)


@dataclass
class RunRecord:
    """Mutable record for a single run."""

    run_id: str
    thread_id: str
    assistant_id: str | None
    status: RunStatus
    on_disconnect: DisconnectMode
    created_at: str = ""
    updated_at: str = ""
    model_name: str | None = None
    

