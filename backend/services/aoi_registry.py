"""AOI registry — maps human-readable aoi_id → demo tile + geographic metadata.

Used by ai_detector / drift_engine / mission_planner to resolve an incoming
`aoi_id` (from the frontend dropdown) to a real MARIDA patch that the
inference pipeline can process end-to-end.

Design notes
-----------
The 4 "canonical" AOIs (gulf_of_mannar, mumbai_offshore, bay_of_bengal_mouth,
arabian_sea_gyre_edge) are the Phase 3 demo targets per CONTEXT D-16. They each
point at a MARIDA val patch chosen for genuine plastic content so the model
produces non-empty detections. MARIDA scenes are globally sourced — none are
physically in the Indian Ocean — so the inference output lat/lon lives in the
MARIDA patch's UTM zone, not the display AOI. That's acceptable for a
hackathon demo (the pipeline wiring is the story); for a production build
we'd pre-stage real Indian Ocean Sentinel-2 tiles per AOI.

Legacy frontend aliases (mumbai, chennai, andaman) are kept so the existing
React dropdown continues to work without changes.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict


class AOIEntry(TypedDict):
    id: str
    name: str
    center: tuple[float, float]          # (lon, lat) in WGS84 — map display center
    bounds: tuple[tuple[float, float], tuple[float, float]]  # [[W, S], [E, N]]
    demo_tile: Path                       # MARIDA patch to run inference on
    origin_lonlat: tuple[float, float]    # vessel origin port (mission planner)


# MARIDA root — single source of truth, matches backend/ml/inference.py default.
# Overrideable via env var `MARIDA_ROOT=/alt/path` for Kaggle / CI.
import os
_MARIDA_DEFAULT = Path(os.environ.get("MARIDA_ROOT", "MARIDA"))


def _patch(patch_id: str) -> Path:
    """Resolve a MARIDA split id like '11-6-18_16PCC_15' to a full .tif path."""
    base = "_".join(patch_id.split("_")[:-1])
    return _MARIDA_DEFAULT / "patches" / f"S2_{base}" / f"S2_{patch_id}.tif"


# Phase 3 canonical AOIs (CONTEXT D-16). Each has real plastic in its demo tile.
_REGISTRY: dict[str, AOIEntry] = {
    "gulf_of_mannar": {
        "id": "gulf_of_mannar",
        "name": "Gulf of Mannar",
        "center": (79.05, 8.85),
        "bounds": ((78.6, 8.5), (79.5, 9.2)),
        "demo_tile": _patch("11-6-18_16PCC_15"),   # 12 plastic px — best
        "origin_lonlat": (78.12, 8.78),             # Tuticorin port
    },
    "mumbai_offshore": {
        "id": "mumbai_offshore",
        "name": "Mumbai Offshore",
        "center": (72.85, 18.95),
        "bounds": ((72.7, 18.8), (73.0, 19.1)),
        "demo_tile": _patch("11-6-18_16PCC_10"),
        "origin_lonlat": (72.80, 18.90),            # Mumbai port
    },
    "bay_of_bengal_mouth": {
        "id": "bay_of_bengal_mouth",
        "name": "Bay of Bengal Mouth",
        "center": (88.00, 21.50),
        "bounds": ((87.5, 21.0), (88.5, 22.0)),
        "demo_tile": _patch("11-6-18_16PCC_13"),
        "origin_lonlat": (88.32, 22.57),            # Kolkata port
    },
    "arabian_sea_gyre_edge": {
        "id": "arabian_sea_gyre_edge",
        "name": "Arabian Sea Gyre Edge",
        "center": (66.50, 15.00),
        "bounds": ((66.0, 14.5), (67.0, 15.5)),
        "demo_tile": _patch("11-6-18_16PCC_25"),
        "origin_lonlat": (70.22, 15.73),            # Karwar naval base
    },
}

# Legacy frontend aliases → canonical AOIs (frontend dropdown compat).
_ALIASES: dict[str, str] = {
    "mumbai": "mumbai_offshore",
    "chennai": "bay_of_bengal_mouth",
    "andaman": "arabian_sea_gyre_edge",
}


def resolve(aoi_id: str) -> AOIEntry | None:
    """Return the AOI entry for `aoi_id`, honoring aliases. None if unknown."""
    canonical = _ALIASES.get(aoi_id, aoi_id)
    return _REGISTRY.get(canonical)


def list_aois() -> list[dict]:
    """List AOIs in the shape the `/api/v1/aois` endpoint expects.

    Matches backend/services/mock_data.get_mock_aois() response format so the
    frontend dropdown renders unchanged.
    """
    return [
        {
            "id": entry["id"],
            "name": entry["name"],
            "center": list(entry["center"]),
            "bounds": [list(entry["bounds"][0]), list(entry["bounds"][1])],
        }
        for entry in _REGISTRY.values()
    ]


def demo_tile_for(aoi_id: str) -> Path | None:
    """Return the demo MARIDA tile path for `aoi_id`, or None if unknown or missing."""
    entry = resolve(aoi_id)
    if entry is None:
        return None
    tile = entry["demo_tile"]
    return tile if tile.exists() else None


def origin_for(aoi_id: str, default: tuple[float, float] = (72.8, 18.9)) -> tuple[float, float]:
    """Return the vessel origin port for `aoi_id`, Mumbai as fallback."""
    entry = resolve(aoi_id)
    return entry["origin_lonlat"] if entry else default
