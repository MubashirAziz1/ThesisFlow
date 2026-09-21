""" Abstract interface for custom agent definition storage. """

from __future__ import annotations

import abc
import logging
from collections.abc import Hashable
from typing import Any, Literal

from pydantic import ValidationError

from deerflow.config.agents_config import AgentConfig

logger = logging.getLogger(__name__)


def parse_agent_config(data: dict[str, Any], name: str) -> AgentConfig:
    """Build an :class:`AgentConfig` from a raw config *document*, shared by both backends.

    Sets ``name`` from the natural key when the document omits it and strips
    unknown keys (e.g. a legacy ``prompt_file``) before validation — identical
    to the pre-refactor ``load_agent_config``.
    """
    data = dict(data)
    if "name" not in data:
        data["name"] = name
    known_fields = set(AgentConfig.model_fields.keys())
    data = {k: v for k, v in data.items() if k in known_fields}
    try:
        return AgentConfig(**data)
    except ValidationError as exc:
        if not any(error["loc"] == ("display_name",) for error in exc.errors()):
            raise
        # A cosmetic value in old/hand-edited storage must not make the agent
        # inaccessible. Retry only without that field: other errors still fail.
        data.pop("display_name", None)
        config = AgentConfig(**data)
        logger.warning("Ignoring invalid stored agent display_name for agent %r", name)
        return config


# Delete outcome, mirroring the agents router's result:
# a row/dir was removed ("deleted"); only a legacy shared-layout entry exists,
# which the current write path never removes ("legacy"); nothing was there
# ("missing"); or a per-user directory exists holding memory/facts data but is
# not a custom agent (no config.yaml), so it is preserved rather than deleting a
# user's memory ("not-custom-agent", #4279).
AgentDeleteOutcome = Literal["deleted", "legacy", "missing", "not-custom-agent"]


class AgentExistsError(Exception):
    """Raised by :meth:`AgentStore.create` when ``(user_id, name)`` already exists."""


class AgentStore(abc.ABC):
    @abc.abstractmethod
    def get(self, name: str, *, user_id: str | None = None) -> AgentConfig:
        """ Return the agent's config. """

    @abc.abstractmethod
    def exists(self, name: str, *, user_id: str | None = None) -> bool:
        """ Return whether ``name`` is already taken for ``user_id``  """

    @abc.abstractmethod
    def get_soul(self, name: str, *, user_id: str | None = None) -> str | None:
        """Return the agent's ``SOUL.md`` content, or ``None`` if unset/empty."""

    @abc.abstractmethod
    def list(self, *, user_id: str | None = None) -> list[AgentConfig]:
        """Return every custom agent owned by ``user_id``, sorted by name."""

    @abc.abstractmethod
    def list_all(self) -> list[tuple[str, AgentConfig]]:
        """Return ``(user_id, config)`` for every agent across all owners.

        Used by the GitHub registry, which scans all users' agents for repo
        bindings. Ordering is deterministic (by ``user_id`` then name).
        """

    @abc.abstractmethod
    def create(self, name: str, config: dict, soul: str, *, user_id: str | None = None) -> None:
        "" "Persist a new agent from the config *document* each write surface builds. """

    @abc.abstractmethod
    def update(self, name: str, config: dict | None, soul: str | None, *, user_id: str | None = None) -> None:
        """ Write an agent's config and/or soul (upsert). """

    @abc.abstractmethod
    def delete(self, name: str, *, user_id: str | None = None) -> AgentDeleteOutcome:
        """Delete an agent and its co-located memory, returning the outcome."""

    @abc.abstractmethod
    def signature(self) -> Hashable:
        """ Return an opaque change token for cache invalidation. """