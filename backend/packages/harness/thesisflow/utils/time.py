""" ISO 8601 timestamp helpers for the Gateway and embedded runtime. """

from __future__ import annotations

from datetime import UTC, datetime, timedelta

__all__ = ["now_iso"]

def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Example: ``"2026-04-27T03:19:46.511479+00:00"``.
    """
    return datetime.now(UTC).isoformat()
