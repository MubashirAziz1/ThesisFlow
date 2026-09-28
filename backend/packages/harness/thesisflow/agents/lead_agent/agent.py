from dataclasses import dataclass
from typing import Any

from packages.harness.thesisflow.config.app_config import AppConfig


@dataclass(frozen=True)
class LeadAgentAssembly:
    """ The compiled graph plus what it was assembled from. """

    graph: Any
    descriptor: Any
    effective_model: str | None = None


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
    # Mode selection precedence, pinned by test_checkpoint_mode.py:
    # - First freeze: the app config owns the process mode; a client-supplied
    #   configurable key is ignored so a direct LangGraph request cannot
    #   reconfigure (or crash) a fresh process.
    # - Once frozen: an internally injected key (run worker / gateway) or the
    #   app config must match the frozen mode; ``freeze_checkpoint_channel_mode``
    #   fails closed on any mismatch, so neither a forged key nor a config.yaml
    #   change can silently reconfigure the process.
    frozen_mode = frozen_checkpoint_channel_mode()
    if frozen_mode is None:
        requested_mode = runtime_app_config.database.checkpoint_channel_mode
    else:
        requested_mode = (config.get("configurable", {}) or {}).get(
            INTERNAL_CHECKPOINT_MODE_KEY,
            runtime_app_config.database.checkpoint_channel_mode,
        )
    mode = freeze_checkpoint_channel_mode(requested_mode)
    # The snapshot cadence travels with the mode: restart-required, frozen
    # from the app config, and deliberately not client-injectable (a forged
    # configurable key must not recompile the channel table either).
    freeze_checkpoint_snapshot_frequency(runtime_app_config.database.checkpoint_delta.snapshot_frequency)
    inject_checkpoint_mode(config, mode)
    return _assemble_lead_agent(config, app_config=runtime_app_config)