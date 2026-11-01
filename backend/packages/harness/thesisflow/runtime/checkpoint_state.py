
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config.database_config import CheckpointChannelMode

@dataclass
class CheckpointStateAccessor:
    graph: Any
    checkpointer: Any
    mode: CheckpointChannelMode
    direct_namespace: bool = False

    @classmethod
    def bind(
        cls,
        graph: Any,
        checkpointer: Any,
        *,
        store: Any | None = None,
        mode: CheckpointChannelMode = "full",
        direct_namespace: bool = False,
    ) -> CheckpointStateAccessor:
        graph.checkpointer = checkpointer
        if store is not None:
            graph.store = store
        return cls(graph=graph, checkpointer=checkpointer, mode=mode, direct_namespace=direct_namespace)
