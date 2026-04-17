"""Runtime behavior flags shared by backend service wrappers."""
from __future__ import annotations

import os


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def strict_mode_enabled() -> bool:
    """When enabled, service wrappers must not silently return mock fallbacks.

    Accepted env vars (any one set truthy enables strict mode):
      - DRIFT_STRICT_MODE
      - DRIFT_DISABLE_FALLBACKS
    """
    return _truthy(os.environ.get("DRIFT_STRICT_MODE")) or _truthy(
        os.environ.get("DRIFT_DISABLE_FALLBACKS")
    )
