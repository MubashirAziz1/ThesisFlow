from __future__ import annotations

import sys
from typing import Any, cast
from dataclasses import field, dataclass
import logging

from .manager import RunManager, RunRecord, RunStartOutcome
from ...config.database_config import CheckpointChannelMode
from ..stream_bridge import StreamBridge
from ...config.app_config import AppConfig
from .schemas import RunStatus
from .stream_cleanup import close_agent_stream
from ..stream_modes import normalize_stream_modes, to_langgraph_stream_modes
from ..serialization import serialize
from ..checkpoint_mode import CHECKPOINT_AGENT_NAME_METADATA_KEY, inject_checkpoint_mode
from ..checkpoint_state import CheckpointStateAccessor

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RunContext:
    """ Infrastructure dependencies for a single agent run. """

    checkpointer: Any
    app_config: AppConfig | None = field(default=None)
    checkpoint_channel_mode: CheckpointChannelMode = "full"
    checkpoint_snapshot_frequency: int | None = None
    

def _build_runtime_context(
    thread_id: str,
    run_id: str,
    app_config: AppConfig | None = None,
    ) -> dict[str, Any]:
    """ Build the dict that becomes ``ToolRuntime.context`` for the run. """

    runtime_ctx: dict[str, Any] = {"thread_id": thread_id, "run_id": run_id}
    
    if app_config is not None:
        runtime_ctx["app_config"] = app_config

    return runtime_ctx

def _agent_graph(agent_result: Any) -> Any:
    """Unwrap the lead assembly, leaving any other factory result untouched."""

    try:
        from ...agents.lead_agent.agent import unwrap_agent_graph
    except Exception:
        return agent_result
    return unwrap_agent_graph(agent_result)


async def run_agent(
    bridge: StreamBridge,
    run_manager: RunManager,
    record: RunRecord,
    *,
    ctx: RunContext,
    agent_factory: Any,
    graph_input: dict,
    config: dict,
    stream_modes: list[str] | None = None,
)-> None:
    
    checkpointer = ctx.checkpointer
    
    run_id = record.run_id
    thread_id = record.thread_id

    agent = None
    runtime_ctx = None

    try:
        normalized_stream_modes = normalize_stream_modes(stream_modes)
        requested_modes: set[str] = set(normalized_stream_modes)
        lg_modes = to_langgraph_stream_modes(normalized_stream_modes)

        start_outcome = await run_manager.try_start(run_id)
        if start_outcome is not RunStartOutcome.started:
            logger.info("Run %s was cancelled before it started", run_id)
            return

        mode = ctx.checkpoint_channel_mode
        inject_checkpoint_mode(config, mode)
        checkpoint_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }
        if checkpointer is not None:
            configurable = config["configurable"]
            selected_configurable = {
                "thread_id": thread_id,
                "checkpoint_ns": configurable.get("checkpoint_ns", ""),
            }
            for selector_key in ("checkpoint_id", "checkpoint_map"):
                if selector_key in configurable:
                    selected_configurable[selector_key] = configurable[selector_key]
            selected_checkpoint_config = {
                "configurable": selected_configurable,
            }

        await bridge.publish(
            run_id,
            "metadata",
            {
                "run_id": run_id,
                "thread_id": thread_id,
            },
        )

        from langchain_core.runnables import RunnableConfig
        from langgraph.runtime import Runtime

        runtime_ctx = _build_runtime_context(
            thread_id,
            run_id,
            ctx.app_config,
        )

        checkpoint_metadata = config.get("metadata")
        if not isinstance(checkpoint_metadata, dict):
            checkpoint_metadata = {}
            config["metadata"] = checkpoint_metadata
        checkpoint_metadata[CHECKPOINT_AGENT_NAME_METADATA_KEY] = "lead_agent"

        config["context"] = runtime_ctx

        # Seed the Pregel runtime (``__pregel_runtime``) so the run context and
        # store plumb through to tools and nodes.
        runtime = Runtime(context=cast(Any, runtime_ctx), store=None)
        config.setdefault("configurable", {})["__pregel_runtime"] = runtime

        runnable_config = RunnableConfig(**config)
        agent = _agent_graph(agent_factory(config=runnable_config))

        accessor = CheckpointStateAccessor.bind(agent, checkpointer, store=None, mode=mode)

        # Attach the checkpointer so thread state is loaded before, and saved
        # after, every run on this thread_id.
        if checkpointer is not None:
            agent.checkpointer = checkpointer

        logger.info("Run %s: streaming with modes %s (requested: %s)", run_id, lg_modes, requested_modes)

        async def _stream_once(input_payload: Any, stream_config: RunnableConfig) -> bool:
            """Publish every chunk; return True if stopped early by an abort request."""

            single_mode = len(lg_modes) == 1
            stream = agent.astream(
                input_payload,
                config=stream_config,
                # One mode yields raw chunks; several modes yield (mode, chunk) tuples.
                stream_mode=lg_modes[0] if single_mode else lg_modes,
            )
            broke_on_abort = False
            try:
                async for item in stream:
                    if record.abort_event.is_set():
                        broke_on_abort = True
                        logger.info("Run %s abort requested — stopping", run_id)
                        break

                    chunk_mode, chunk = (lg_modes[0], item) if single_mode else item
                    await bridge.publish(
                        run_id,
                        _lg_mode_to_sse_event(chunk_mode),
                        serialize(chunk, mode=chunk_mode),
                    )
            finally:
                close_error = sys.exception()
                try:
                    await close_agent_stream(stream)
                except Exception:
                    abort_requested = broke_on_abort or record.abort_event.is_set()
                    if close_error is None and not abort_requested:
                        raise
                    if abort_requested:
                        logger.warning("Could not close aborted agent stream for run %s", run_id, exc_info=True)
                    else:
                        logger.debug("Could not close agent stream for run %s", run_id, exc_info=True)
            return broke_on_abort

        aborted = await _stream_once(graph_input, runnable_config)
        await run_manager._persist_status(record, RunStatus.interrupted if aborted else RunStatus.success)

    except Exception as exc:
        error_msg = f"{exc}"
        logger.exception("Run %s failed: %s", run_id, error_msg)
        record.error = error_msg
        await run_manager._persist_status(record, RunStatus.error)
        await bridge.publish(
                run_id,
                "error",
                {
                    "message": error_msg,
                    "name": type(exc).__name__,
                },
            )
    
    finally:
        try:
            await bridge.publish_end(run_id)
        finally:            
            # Drop graph and per-run payload references before the terminal
            # worker task itself becomes collectable.
            agent = None
            runtime_ctx = None
            graph_input = {}


def _lg_mode_to_sse_event(mode: str) -> str:
    """ Map LangGraph internal stream_mode name to SSE event name. """
    # All LG modes map 1:1 to SSE event names — "messages" stays "messages"

    return mode
