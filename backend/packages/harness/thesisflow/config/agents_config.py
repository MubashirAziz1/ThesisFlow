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


def _validate_display_name(value: object) -> object:
    # Check before trimming so leading/trailing controls cannot disappear.
    # Keep ordinary RTL text, ZWNJ in Persian/Indic text and ZWJ in emoji.
    if isinstance(value, str):
        if re.search(r"[\x00-\x1f\x7f-\x9f\u00ad\u061c\u200b\u200e-\u200f\u2028-\u202e\u2060-\u2069\ufeff]", value):
            raise ValueError("Display name must not contain control characters or invisible formatting controls")
        if value.strip() and all(unicodedata.category(char)[0] in {"C", "M", "Z"} for char in value):
            raise ValueError("Display name must contain visible text")
    return value


AgentDisplayName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100), BeforeValidator(_validate_display_name)]

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



def load_agent_config(name: str | None, *, user_id: str | None = None) -> AgentConfig | None:
    """Load the custom or default agent's config.

    Dispatches to the configured agent store (``agent_storage.backend``): the
    ``file`` backend reads the per-user layout first and falls back to the legacy
    shared layout; the ``db`` backend reads the shared ``agents`` table. Behaviour
    and error semantics are unchanged from the historical file-only loader.

    """
    if name is None:
        return None
    
    from deerflow.persistence.agents import get_agent_store

    return get_agent_store().get(name, user_id=user_id)