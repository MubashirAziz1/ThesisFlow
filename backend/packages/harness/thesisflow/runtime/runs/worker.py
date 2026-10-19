from __future__ import annotations

import sys
from typing import Any
from dataclasses import field, dataclass
import logging
from fastapi import Request


from .manager import RunManager, RunRecord, RunStartOutcome
from ..stream_bridge import StreamBridge
from ...config.app_config import AppConfig
from .schemas import RunStatus
from .stream_cleanup import close_agent_stream
from ..stream_modes import normalize_stream_modes, to_langgraph_stream_modes
from ..serialization import serialize

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RunContext:
    """ Infrastructure dependencies for a single agent run. """

    app_config: AppConfig | None = field(default=None)

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
    
    run_id = record.run_id
    thread_id = record.thread_id
    llm_error_fallback_message: str | None = None

    started = False

    try:
        normalized_stream_modes = normalize_stream_modes(stream_modes)
        requested_modes: set[str] = set(normalized_stream_modes)
        lg_modes = to_langgraph_stream_modes(normalized_stream_modes)

        start_outcome = await run_manager.try_start(run_id)
        started = True

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


        runnable_config = RunnableConfig(**config)
        agent = _agent_graph(agent_factory(config=runnable_config))

        logger.info("Run %s: streaming with modes %s (requested: %s)", run_id, lg_modes, requested_modes)

        async def _stream_once(input_payload: Any, stream_config: RunnableConfig) -> None:
            file_tool_chunk_batcher = None
            try:
                if len(lg_modes) == 1:
                    # Single mode, no subgraphs: astream yields raw chunks
                    single_mode = lg_modes[0]
                    stream = agent.astream(input_payload, config=stream_config, stream_mode=single_mode)
                    broke_on_abort = False
                    try:
                        async for chunk in stream:
                            if record.abort_event.is_set():
                                broke_on_abort = True
                                logger.info("Run %s abort requested — stopping", run_id)
                                break
                            
                            sse_event = _lg_mode_to_sse_event(single_mode)
                            single_payload = serialize(chunk, mode=single_mode)
                    
                            await bridge.publish(run_id, sse_event, single_payload)
    
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
                    return
            except Exception as exc:
                logger.exception("Run %s failed: %s", run_id, exc)
        await _stream_once(graph_input, runnable_config)

    except Exception as exc:
        error_msg = f"{exc}"
        logger.exception("Run %s failed: %s", run_id, error_msg)
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
            try:
                if journal is not None:
                    try:
                        await journal.close(flush=not record.ownership_lost)
                    except Exception:
                        logger.warning("Failed to close journal for run %s", run_id, exc_info=True)
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



        

           
      