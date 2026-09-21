""" Custom agent definition persistence — abstract store + file/db backends. """

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from deerflow.persistence.agents.base import (
    AgentDeleteOutcome,
    AgentExistsError,
    AgentStore,
    parse_agent_config,
)
from deerflow.persistence.agents.model import AgentRow

if TYPE_CHECKING:
    from deerflow.config.app_config import AppConfig