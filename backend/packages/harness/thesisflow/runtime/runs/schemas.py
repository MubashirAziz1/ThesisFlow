"""Run status and disconnect mode enums."""

from enum import StrEnum

class DisconnectMode(StrEnum):
    """Behaviour when the SSE consumer disconnects."""

    cancel = "cancel"
    continue_ = "continue"