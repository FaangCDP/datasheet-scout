"""Shared environment utilities — safe integer parsing with optional min_value guard."""

import os


def parse_int_env(name: str, default: int, min_value: int | None = None) -> int:
    """Parse an environment variable as int safely.

    - Empty string, whitespace-only, or non‑numeric values → default.
    - Enforces min_value when provided (rejects 0 and negatives).
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        val = int(raw.strip())
    except (TypeError, ValueError):
        return default
    if min_value is not None and val < min_value:
        return default
    return val