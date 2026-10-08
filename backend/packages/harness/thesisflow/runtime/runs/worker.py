from __future__ import annotations

from typing import Any
from dataclasses import field, dataclass
import logging
from langchain_core.runnables import RunnableConfig


from .manager import RunManager, RunRecord
from ...config.app_config import AppConfig
from .schemas import RunStatus

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
    run_manager: RunManager,
        record: RunRecord,
        *,
        ctx: RunContext,
        agent_factory: Any,
        graph_input: dict,
        config: dict,
)-> None:
    
    run_id = record.run_id

    start_outcome = await run_manager.try_start(run_id)
    if start_outcome.value != "started":
        return None

    try:
        runnable_config = RunnableConfig(**config)
        agent = _agent_graph(agent_factory(config=runnable_config))
        result = await agent.ainvoke(graph_input, config=runnable_config)
        await run_manager.set_status_if_not_cancelled(run_id, RunStatus.success)
        return result
    except Exception as exc:
        await run_manager.set_status_if_not_cancelled(run_id, RunStatus.error, error=str(exc))
        raise



        

           
      