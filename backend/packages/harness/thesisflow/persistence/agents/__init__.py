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

__all__ = [
    "AgentRow",
    "AgentStore",
    "get_agent_store",
    "make_agent_store",
]

file_store_singleton: AgentStore | None = None

def make_agent_store(config: AppConfig) -> AgentStore:
    """ Build (or reuse) the store selected by ``config.agent_storage.backend``. """

    if config.agent_storage.backend == "db":
        db_backend = config.database.backend
        if db_backend not in ("sqlite", "postgres"):
            raise ValueError(
                f"agent_storage.backend='db' requires database.backend to be 'sqlite' or 'postgres', "
                f"but database.backend is '{db_backend}'. A 'memory' database is per-process and cannot "
                "share agent definitions across nodes; set database.backend accordingly or use "
                "agent_storage.backend='file'."
            )
        from deerflow.persistence.agents.sql import SqlAgentStore

        return SqlAgentStore(config.database.app_sync_sqlalchemy_url)

    return _file_store()

def get_agent_store() -> AgentStore:
    """ Return the store for the current process's configuration. """
    from deerflow.config.app_config import AppConfig, get_app_config

    try:
        config = get_app_config()
    except FileNotFoundError:
        if os.getenv("DEER_FLOW_CONFIG_PATH"):
            raise
        # ``get_app_config()`` also loads optional nested config files. Only
        # fall back when the main config itself is absent.
        try:
            AppConfig.resolve_config_path()
        except FileNotFoundError:
            return _file_store()
        raise
    return make_agent_store(config)


def _file_store() -> AgentStore:
    global _file_store_singleton
    if _file_store_singleton is None:
        from deerflow.persistence.agents.file import FileAgentStore

        _file_store_singleton = FileAgentStore()
    return _file_store_singleton