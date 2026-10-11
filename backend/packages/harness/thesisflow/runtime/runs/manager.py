"""In-memory run registry."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
import uuid
import asyncio



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
    abort_action: str = "interrupt"
    abort_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    model_name: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)
    

class RunManager:
    """  In-memory run registry with optional persistent RunStore backing. """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_stop: asyncio.Event | None = None
        self._orphan_recovery_task: asyncio.Task[None] | None = None
        self._run_ownership_config = None
        self._worker_id = f"local-{os.getpid()}"

    @property
    def heartbeat_enabled(self) -> bool:
        """Return ``True`` when the heartbeat background task should run."""
        if self._run_ownership_config is None:
            return False
        logger.warning("_run_ownership_config is accidentally becomes Not None")
        return False
    
    async def create_or_reject(
        self,
        thread_id: str,
        assistant_id: str | None = None,
        *,
        on_disconnect: DisconnectMode = DisconnectMode.cancel,
        model_name: str | None = None,
    ) -> RunRecord:
        """Atomically admit a normal agent run for a thread."""

        return await self._admit_thread_operation(
            thread_id,
            assistant_id,
            on_disconnect=on_disconnect,
            model_name=model_name,
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

        logger.info("Run created: run_id=%s thread_id=%s", run_id, thread_id)
        return record


    async def start_heartbeat(self) -> None:
        """ Start the background lease-renewal task. """

        if not self.heartbeat_enabled:
            return
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_stop = asyncio.Event()
        task = asyncio.create_task(self._heartbeat_loop())
        task.set_name("deerflow-run-lease-heartbeat")
        self._heartbeat_task = task
        logger.info("Run lease heartbeat started for worker %s", self._worker_id)

    async def stop_heartbeat(self, *, timeout: float = 5.0) -> None:
        """Stop the background heartbeat task within ``timeout`` seconds."""

        was_running = self._heartbeat_task is not None
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            _, pending = await asyncio.wait(
                (self._heartbeat_task,),
                timeout=max(0.0, timeout),
            )
            if pending:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
        self._heartbeat_task = None
        self._heartbeat_stop = None
        if was_running:
            logger.info("Run lease heartbeat stopped for worker %s", self._worker_id)

    async def _drain_orphan_recovery_task(self, *, timeout: float) -> None:
        """Boundedly await the supervised recovery pass during shutdown."""
        task = self._orphan_recovery_task
        if task is None or task.done():
            return
        _, pending = await asyncio.wait((task,), timeout=max(0.0, timeout))
        if pending:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            logger.warning(
                "Orphan recovery drain exceeded %.1fs on shutdown; cancelled the active pass",
                timeout,
            )

    async def _persist_status(self, record: RunRecord, status: RunStatus) -> bool:
        """Store a terminal status on the in-memory run record."""

        record.status = status
        record.updated_at = _now_iso()
        return True

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        """ Cancel and bounded-await all in-flight runs on process shutdown. """

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        async with self._lock:
            inflight = [record for record in self._runs.values() if record.status in (RunStatus.pending, RunStatus.running) and record.task is not None and not record.task.done()]
            for record in inflight:
                record.abort_action = "interrupt"
                record.abort_event.set()
                record.task.cancel() 

        await self.stop_heartbeat(timeout=max(0.0, deadline - loop.time()))

        if not inflight:
            await self._drain_orphan_recovery_task(timeout=max(0.0, deadline - loop.time()))
            return

        tasks = [record.task for record in inflight]
        _, pending = await asyncio.wait(tasks, timeout=max(0.0, deadline - loop.time()))

        to_persist: list[RunRecord] = []
        async with self._lock:
            for record in inflight:
                task = record.task
                if task not in pending and not task.cancelled():
                    # Completed on its own — retrieve any surfaced exception so it
                    # is not reported as "never retrieved", and keep its status.
                    task.exception()  # type: ignore[union-attr]  # done & not cancelled
                    continue
                if record.status in (RunStatus.pending, RunStatus.running):
                    record.status = RunStatus.interrupted
                    record.updated_at = _now_iso()
                to_persist.append(record)

        if to_persist:
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.warning("Run drain budget exhausted before persisting %d interrupted run(s) on shutdown", len(to_persist))
            else:
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*(self._persist_status(record, RunStatus.interrupted) for record in to_persist), return_exceptions=True),
                        timeout=remaining,
                    )
                except TimeoutError:
                    logger.warning("Run drain status persistence exceeded the %.1fs budget; %d record(s) may not be persisted", timeout, len(to_persist))
                else:
                    for record, result in zip(to_persist, results):
                        if isinstance(result, Exception):
                            logger.warning("Unexpected error persisting interrupted status for run %s during shutdown: %r", record.run_id, result)
                        elif result is False:
                            logger.warning("Could not persist interrupted status for run %s during shutdown", record.run_id)

        if pending:
            logger.warning("Run drain exceeded %.1fs on shutdown; %d run task(s) still active and may race checkpointer teardown", timeout, len(pending))
        logger.info("Drained %d in-flight run(s) on shutdown (%d settled within %.1fs)", len(inflight), len(inflight) - len(pending), timeout)
        await self._drain_orphan_recovery_task(timeout=max(0.0, deadline - loop.time()))







