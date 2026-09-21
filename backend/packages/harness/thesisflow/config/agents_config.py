"""Configuration and loaders for custom agents."""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator, model_validator

from deerflow.config.paths import get_paths
from deerflow.knowledge_scope import KnowledgeScope
from deerflow.runtime.user_context import get_effective_user_id

logger = logging.getLogger(__name__)

SOUL_FILENAME = "SOUL.md"
AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
MAX_AGENT_OUTPUT_TOKENS = 200_000



class AgentConfig(BaseModel):
    """Configuration for a custom agent."""

    name: str
    display_name: AgentDisplayName | None = None
    description: str = ""
    model: str | None = None
    tool_groups: list[str] | None = None
    # skills controls which skills are discoverable and may be activated by the
    # agent. It does not activate their allowed-tools policies at construction:
    # - None (or omitted): load all enabled skills (default fallback behavior)
    # - [] (explicit empty list): disable all skills
    # - ["skill1", "skill2"]: load only the specified skills
    skills: list[str] | None = None
    # Stable MCP installation IDs. None inherits all; [] selects none.
    # This is tool selection, not a replacement for host authorization.


# Fields explicitly managed by agent-update surfaces. Anything else declared
# on :class:`AgentConfig` — currently ``github``, and any future field — is
# preserved verbatim by :func:`preserve_non_managed_fields` so update surfaces
# do not silently drop hand-authored configuration. Some surfaces expose only a
# subset of these managed fields (for example, the harness ``update_agent``
# tool does not accept model-behavior arguments), so they must carry their
# unsupported managed fields forward explicitly when rewriting config.yaml.
# ``name`` is included because updaters always re-emit it from the directory
# name (it must never come from the request body).
MANAGED_AGENT_CONFIG_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "model",
        "tool_groups",
        "skills",
    }
)

def load_agent_config(name: str | None, *, user_id: str | None = None) -> AgentConfig | None:
    """Load the custom or default agent's config.

    Dispatches to the configured agent store (``agent_storage.backend``): the
    ``file`` backend reads the per-user layout first and falls back to the legacy
    shared layout; the ``db`` backend reads the shared ``agents`` table. Behaviour
    and error semantics are unchanged from the historical file-only loader.

    Args:
        name: The agent name.
        user_id: Owner of the agent. Defaults to the effective user from the
            current request context.

    Returns:
        AgentConfig instance, or ``None`` if ``name`` is ``None``.

    Raises:
        FileNotFoundError: If the agent does not exist.
        ValueError: If the stored config cannot be parsed.
    """
    if name is None:
        return None
    # Lazy import: the store package imports back from this module.
    from deerflow.persistence.agents import get_agent_store

    return get_agent_store().get(name, user_id=user_id)