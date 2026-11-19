"""JSON helpers that PostgreSQL jsonb can store."""

from __future__ import annotations

import json
import math
from typing import Any


def _normalize(value: Any) -> Any:
    """Replace non-finite floats so jsonb does not reject the payload."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def dumps_json_safe(obj: object) -> str:
    """Dump JSON with non-finite floats stored as null."""
    return json.dumps(_normalize(obj), ensure_ascii=False)
