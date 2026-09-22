"""In-memory run registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass
import uuid


from .schemas import DisconnectMode, RunStatus
from packages.harness.thesisflow.utils.time import now_iso as _now_iso

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

class RunManager:
    """  In-memory run registry with optional persistent RunStore backing. """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._runs_by_thread: dict[str, dict[str, None]] = {}
        self._worker_id = worker_id or _generate_worker_id()

    async def create_or_reject(
        self,
        thread_id: str,
        assistant_id: str | None = None,
        *,
        on_disconnect: DisconnectMode = DisconnectMode.cancel,
        model_name: str | None = None,
        user_id: str | None = None,
    ) -> RunRecord:
        """Atomically admit a normal agent run for a thread."""

        return await self._admit_thread_operation(
            thread_id,
            assistant_id,
            on_disconnect=on_disconnect,
            model_name=model_name,
            user_id=user_id,
        )

    async def _admit_thread_operation(
        self,
        thread_id: str,
        assistant_id: str | None = None,
        *,
        on_disconnect: DisconnectMode = DisconnectMode.cancel,
        model_name: str | None = None,
    ) -> RunRecord:
        """ Atomically check for inflight runs and create a new one. """
        run_id = str(uuid.uuid4())
        now = _now_iso()

        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id=assistant_id,
            status=RunStatus.pending,
            on_disconnect=on_disconnect,
            created_at=now,
            updated_at=now,
            model_name=model_name,
        )

        async with self._lock:

            self._runs[run_id] = record
            self._index_run_locked(record)


        logger.info("Run created: run_id=%s thread_id=%s", run_id, thread_id)
        return record
    

