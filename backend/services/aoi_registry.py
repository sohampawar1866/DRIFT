"""AOI registry — resolves aoi_id strings to geographic metadata.

The system uses coordinate-based custom AOIs exclusively.
AOI IDs follow the format: custom_{lon}_{lat}
"""
from __future__ import annotations

from typing import TypedDict


class AOIEntry(TypedDict):
    id: str
    name: str
    center: tuple[float, float]
    bounds: tuple[tuple[float, float], tuple[float, float]]


_CUSTOM_AOI_HALF_SPAN_DEG = 0.03


def _parse_custom_aoi(aoi_id: str) -> tuple[float, float] | None:
    """Extract (lon, lat) from a custom_{lon}_{lat} AOI ID."""
    if not aoi_id.startswith("custom_"):
        return None
    parts = aoi_id.split("_")
    if len(parts) != 3:
        return None
    try:
        return (float(parts[1]), float(parts[2]))
    except ValueError:
        return None


def resolve(aoi_id: str) -> AOIEntry | None:
    """Resolve an aoi_id to an AOIEntry. Returns None for unknown IDs."""
    coords = _parse_custom_aoi(aoi_id)
    if coords is None:
        return None
    lon, lat = coords
    return {
        "id": aoi_id,
        "name": f"Custom ({lon:.4f}, {lat:.4f})",
        "center": (lon, lat),
        "bounds": (
            (lon - _CUSTOM_AOI_HALF_SPAN_DEG, lat - _CUSTOM_AOI_HALF_SPAN_DEG),
            (lon + _CUSTOM_AOI_HALF_SPAN_DEG, lat + _CUSTOM_AOI_HALF_SPAN_DEG),
        ),
    }


def list_aois() -> list[dict]:
    """List AOIs. Returns empty — the system uses only coordinate-based selection."""
    return []


def origin_for(aoi_id: str, default: tuple[float, float] | None = None) -> tuple[float, float]:
    """Return the vessel origin for the given AOI. Parses custom coordinates."""
    coords = _parse_custom_aoi(aoi_id)
    if coords is not None:
        return coords
    return default or (0.0, 0.0)
