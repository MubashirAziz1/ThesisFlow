from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from packages.harness.thesisflow.config.app_config import AppConfig, get_app_config


@dataclass(frozen=True)
class LeadAgentAssembly:
    """ The compiled graph plus what it was assembled from. """

    graph: Any
    descriptor: Any
    effective_model: str | None = None


def _get_runtime_config(config: RunnableConfig) -> dict:
    """Merge legacy configurable options with LangGraph runtime context."""

    cfg = dict(config.get("configurable", {}) or {})
    context = config.get("context", {}) or {}
    if isinstance(context, dict):
        cfg.update(context)
    return cfg

def _assemble_lead_agent(config: RunnableConfig, *, app_config: AppConfig) -> LeadAgentAssembly:
   

    cfg = _get_runtime_config(config)
    resolved_app_config = app_config
    

    requested_model_name: str | None = cfg.get("model_name") or cfg.get("model")
    is_plan_mode = cfg.get("is_plan_mode", False)
    agent_name = validate_agent_name(cfg.get("agent_name"))

    agent_config = load_agent_config(agent_name, user_id=resolved_user_id) if not is_bootstrap else None
   
    config.setdefault("configurable", {})["subagent_enabled"] = subagent_enabled
    if isinstance(config.get("context"), dict):
        config["context"]["subagent_enabled"] = subagent_enabled
    available_skills = _available_skill_names(agent_config, is_bootstrap)
    # Custom agent model from agent config (if any), or None to let _resolve_model_name pick the default
    agent_model_name = agent_config.model if agent_config and agent_config.model else None

    # thinking / reasoning precedence: request > custom agent default > runtime
    # default (issue #4336). See ``_resolve_runtime_option`` for the falsy-vs-unset
    # handling.
    thinking_enabled = getattr(agent_config, "thinking_enabled", None) if agent_config else None
    reasoning_effort = getattr(agent_config, "reasoning_effort", None) if agent_config else None


    # Per-agent sampling overrides (temperature / max_tokens) layered on top of
    # the resolved model profile (issue #4336). None when the agent set none.
    agent_model_settings = getattr(agent_config, "model_settings", None) if agent_config else None
    agent_model_overrides = agent_model_settings.model_dump(exclude_none=True) if agent_model_settings else None

    # Final model name resolution: request → agent config → global default, with fallback for unknown names
    model_name = _resolve_model_name(requested_model_name or agent_model_name, app_config=resolved_app_config)

    # Phase 3: enforce model:use authorization. On deny, fall back to the first
    # allowed model (graceful) rather than crashing the run (RFC §9).
    model_name = _authorize_model_name(model_name, context=cfg, app_config=resolved_app_config)

    model_config = resolved_app_config.get_model_config(model_name)

    if model_config is None:
        raise ValueError("No chat model could be resolved. Please configure at least one model in config.yaml or provide a valid 'model_name'/'model' in the request.")
    # Normalize the request against the model's reasoning contract (issue #5073)
    # so the run metadata, the assembly descriptor and the factory agree on the
    # effective policy: required-thinking models turn the flag back on, an
    # unsupported model turns it off, and a restricted effort vocabulary maps
    # the generic value onto the provider's own.
    reasoning_contract = resolve_reasoning_contract(model_config)
    resolved_reasoning = resolve_reasoning_request(reasoning_contract, thinking_enabled=thinking_enabled, reasoning_effort=reasoning_effort)
    if "thinking_unsupported" in resolved_reasoning.adjustments:
        logger.warning(f"Thinking mode is enabled but model '{model_name}' does not support it; fallback to non-thinking mode.")
    elif resolved_reasoning.adjustments:
        logger.info("Model '%s': reasoning request adjusted by its capability contract (%s)", model_name, ", ".join(resolved_reasoning.adjustments))
    thinking_enabled = resolved_reasoning.thinking_enabled
    if reasoning_contract.source == "contract":
        # Legacy profiles keep forwarding the raw request (the factory strips
        # what the profile cannot honor, exactly as before); declared
        # contracts hand the factory the provider value they resolved to.
        reasoning_effort = resolved_reasoning.reasoning_effort

    logger.info(
        "Create Agent(%s) -> thinking_enabled: %s, reasoning_effort: %s, model_name: %s, is_plan_mode: %s, subagent_enabled: %s, max_concurrent_subagents: %s, max_total_subagents: %s",
        agent_name or "default",
        thinking_enabled,
        reasoning_effort,
        model_name,
        is_plan_mode,
        subagent_enabled,
        max_concurrent_subagents,
        max_total_subagents,
    )

    
   

    system_prompt = apply_prompt_template(
        subagent_enabled=subagent_enabled,
        max_concurrent_subagents=max_concurrent_subagents,
        max_total_subagents=max_total_subagents,
        agent_name=agent_name,
        available_skills=available_skills,
        app_config=resolved_app_config,
        deferred_names=setup.deferred_names,
        mcp_routing_hints_section=mcp_routing_hints_section,
        user_id=resolved_user_id,
        skill_names=skill_setup.skill_names or None,
        allowed_subagents=allowed_subagents,
        subagent_execution_capacity=subagent_execution_capacity,
        interaction_policy=interaction_policy,
        memory_enabled=memory_enabled,
    )
    graph = create_agent(
        model=chat_model,
        tools=final_tools,
        middleware=normalize_middleware_state_schemas(middlewares, mode),
        system_prompt=system_prompt,
        state_schema=get_thread_state_schema(mode),
        context_schema=dict,
    )
    return _complete_assembly(
        config=config,
        graph=graph,
        namespace="deerflow",
        agent_name=agent_name or "lead-agent",
        requested_model=requested_model_name or agent_model_name,
        effective_model=model_name,
        model_config=model_config,
        model_overrides=agent_model_overrides,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
        rendered_base_prompt=system_prompt,
        tools=final_tools,
        middlewares=middlewares,
        deferred_names=setup.deferred_names,
        enabled_skills=enabled_skills,
        effective_policies={
            "bootstrap": False,
            "non_interactive": non_interactive,
            "plan_mode": is_plan_mode,
            "subagents": _subagent_release_policy(
                resolved_app_config,
                enabled=subagent_enabled,
                max_concurrent=max_concurrent_subagents,
                max_total=max_total_subagents,
                allowed_subagents=allowed_subagents,
            ),
            "deferred_tools": {
                "enabled": resolved_app_config.tool_search.enabled,
                "catalog_hash": setup.catalog_hash,
            },
            "deferred_skills": skill_search_enabled,
        },
    )


def assemble_lead_agent(
    config: RunnableConfig,
    *,
    app_config: AppConfig | None = None,
) -> LeadAgentAssembly:
    """ Return the compiled lead graph together with its assembly descriptor. """

    runtime_config = _get_runtime_config(config)
    runtime_app_config = app_config or runtime_config.get("app_config")
    if not isinstance(runtime_app_config, AppConfig):
        runtime_app_config = get_app_config()
   
    return _assemble_lead_agent(config, app_config=runtime_app_config)