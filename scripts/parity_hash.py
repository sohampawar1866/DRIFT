"""Deterministic parity hashing per D-14.

Hash = SHA-256 of canonical JSON(model_dump) after float rounding to
`ndigits` decimal places (default 6). CPU-only determinism + fixed seeds
are the caller's responsibility; this module only guarantees that equal
(modulo 6-decimal fp drift) pydantic models hash identically.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

DEFAULT_NDIGITS = 6


def normalize_floats(obj: Any, ndigits: int = DEFAULT_NDIGITS) -> Any:
    """Recursively round every float leaf; preserve dict/list/scalar structure."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: normalize_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_floats(x, ndigits) for x in obj]
    if isinstance(obj, tuple):
        return [normalize_floats(x, ndigits) for x in obj]   # JSON has no tuple
    return obj


def parity_hash(model: BaseModel, ndigits: int = DEFAULT_NDIGITS) -> str:
    """SHA-256 over `sort_keys=True` JSON of a float-normalized pydantic dump."""
    raw = json.loads(model.model_dump_json())
    normalized = normalize_floats(raw, ndigits=ndigits)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parity_hash_json(payload_json: str, ndigits: int = DEFAULT_NDIGITS) -> str:
    """Same as parity_hash but for a raw JSON string (used on prebake reloads)."""
    raw = json.loads(payload_json)
    normalized = normalize_floats(raw, ndigits=ndigits)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    # Minimal self-check (doc/demo): `python scripts/parity_hash.py path/to/file.json`
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/parity_hash.py <json_file>")
    print(parity_hash_json(open(sys.argv[1], encoding="utf-8").read()))
