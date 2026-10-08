from dataclasses import dataclass
from typing import Any
from fastapi import Request
import logging

from langchain_core.runnables import RunnableConfig
from langchain.agents import create_agent

from packages.harness.thesisflow.config.app_config import AppConfig, get_app_config
from ...models.factory import create_chat_model
from prompt import apply_prompt_template


logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class LeadAgentAssembly:
    """ The compiled graph plus what it was assembled from. """

    graph: Any
    effective_model: str | None = None
def unwrap_agent_graph(agent_result: Any) -> Any:
    """ Unwrap a lead assembly, leaving any other factory result untouched. """
    
    return agent_result.graph if isinstance(agent_result, LeadAgentAssembly) else agent_result


def _get_runtime_config(config: RunnableConfig) -> dict:

    cfg = dict(config.get("configurable", {}) or {})
    return cfg

def _assemble_lead_agent(config: RunnableConfig, *, app_config: AppConfig) -> LeadAgentAssembly:
   

    cfg = _get_runtime_config(config)
    resolved_app_config = app_config

    # Work is required in this section. Take care of it. Mubashir Aziz. Good Luck
    model_name: str | None = cfg.get("model_name") or cfg.get("model")
    is_plan_mode = cfg.get("is_plan_mode", False)
    thinking_enabled: str | None = cfg.get("thinking_enabled", False)
    reasoning_effort: str | None = cfg.get("reasoning_effort", False)

    model_config = resolved_app_config.get_model_config(model_name)
    if model_config is None:
        raise ValueError("No chat model could be resolved. Please configure at least one model in config.yaml or provide a valid 'model_name'/'model' in the request.")

    logger.info(
        "Create Agent(%s) -> thinking_enabled: %s, reasoning_effort: %s, model_name: %s, is_plan_mode: %s.",
        "lead-agent",
        thinking_enabled,
        reasoning_effort,
        model_name,
        is_plan_mode,
    )

    # Inject run metadata for LangSmith trace tagging
    if "metadata" not in config:
        config["metadata"] = {}

    config["metadata"].update(
        {
            "agent_name": "lead-agent",
            "model_name": model_name,
            "thinking_enabled": thinking_enabled,
            "reasoning_effort": reasoning_effort,
            "is_plan_mode": is_plan_mode,
        }
    )

    chat_model = create_chat_model(name=model_name, thinking_enabled=thinking_enabled, reasoning_effort=reasoning_effort, app_config=resolved_app_config, attach_tracing=False)
    system_prompt = apply_prompt_template()
    graph = create_agent(
        model=chat_model,
        system_prompt=system_prompt,
    )

    return LeadAgentAssembly(graph=graph , effective_model=model_name)

def assemble_lead_agent(
    config: RunnableConfig,
    request: Request,
) -> LeadAgentAssembly:
    """ Return the compiled lead graph together with its assembly descriptor. """

    runtime_app_config = request.app.state.app_config
    return _assemble_lead_agent(config, app_config=runtime_app_config)
  
