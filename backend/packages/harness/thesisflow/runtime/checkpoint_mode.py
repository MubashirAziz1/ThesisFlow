""" Dual-mode checkpoint channel safety: mode freeze, metadata markers, and the fail-closed gate. """

from __future__ import annotations

from typing import Any
from ..config.database_config import DEFAULT_CHECKPOINT_SNAPSHOT_FREQUENCY, CheckpointChannelMode

_frozen_checkpoint_channel_mode: CheckpointChannelMode | None = None
_frozen_checkpoint_snapshot_frequency: int | None = None

def frozen_checkpoint_channel_mode() -> CheckpointChannelMode | None:
    """Return the process-frozen checkpoint channel mode, if already frozen."""
    return _frozen_checkpoint_channel_mode

def freeze_checkpoint_channel_mode(mode: CheckpointChannelMode) -> CheckpointChannelMode:
    global _frozen_checkpoint_channel_mode
    if _frozen_checkpoint_channel_mode is None:
        _frozen_checkpoint_channel_mode = mode

    return _frozen_checkpoint_channel_mode

def frozen_checkpoint_snapshot_frequency() -> int | None:
    """Return the process-frozen delta snapshot frequency, if already frozen."""
    return _frozen_checkpoint_snapshot_frequency



def freeze_checkpoint_snapshot_frequency(snapshot_frequency: int) -> int:
    """ Freeze the delta snapshot cadence alongside the channel mode. """
    global _frozen_checkpoint_snapshot_frequency
    if snapshot_frequency <= 0:
        raise ValueError("snapshot frequency must be positive")
    if _frozen_checkpoint_snapshot_frequency is None:
        _frozen_checkpoint_snapshot_frequency = snapshot_frequency
    
    return _frozen_checkpoint_snapshot_frequency
