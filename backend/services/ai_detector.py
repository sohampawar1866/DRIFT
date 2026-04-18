"""ai_detector — service wrapper over backend.ml.inference.run_inference.

Runs real inference only (no mock fallback). Tile resolution prefers explicit
input tile path, then live/cached STAC imagery.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.services.aoi_registry import resolve
from backend.services.env_service import get_environment_summary
from backend.physics.bio_fouling import apply_environmental_biofouling

logger = logging.getLogger(__name__)

_CUSTOM_AOI_HALF_SPAN_DEG = 0.03


def _predicted_class(confidence: float) -> str:
    if confidence >= 0.80:
        return "macroplastic_high_risk"
    if confidence >= 0.60:
        return "macroplastic_likely"
    return "macroplastic_low_conf"


def _detection_fc_to_api_shape(fc, aoi_id: str, env_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Adapt FROZEN DetectionFeatureCollection → API dict shape.

    Per-feature `properties`:
        id: "{aoi_id}_{NNN}"              synthesized from index
        confidence: float                 mapped from conf_adj (biofouling-decayed)
        area_sq_meters: float             renamed from area_m2
        age_days: int                     renamed from age_days_est
        type: "macroplastic"              fixed literal
        fraction_plastic: float           sub-pixel coverage
    """
    features: list[dict[str, Any]] = []
    env_meta = env_meta or {}
    decay_k = float(env_meta.get("confidence_decay_k", 0.03))
    water_temp = env_meta.get("water_temp_c")
    chlorophyll = env_meta.get("chlorophyll_mg_m3")

    for i, feat in enumerate(fc.features):
        p = feat.properties
        geom = feat.geometry.model_dump() if hasattr(feat.geometry, "model_dump") else feat.geometry
        conf = round(p.conf_adj, 3)
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "id": f"{aoi_id}_{i:03d}",
                "confidence": conf,
                "area_sq_meters": round(p.area_m2, 2),
                "age_days": p.age_days_est,
                "type": "macroplastic",
                "fraction_plastic": round(p.fraction_plastic, 3),
                "predicted_class": _predicted_class(conf),
                "confidence_decay_k": round(decay_k, 6),
                "water_temp_c": None if water_temp is None else round(float(water_temp), 3),
                "chlorophyll_mg_m3": None if chlorophyll is None else round(float(chlorophyll), 4),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _env_bbox_for(aoi_id: str, bbox_override: list[float] | None) -> list[float]:
    """Resolve the bounding box for environmental data lookup."""
    if bbox_override is not None:
        return bbox_override
    entry = resolve(aoi_id)
    if entry is not None:
        (west, south), (east, north) = entry["bounds"]
        return [west, south, east, north]
    custom = _bbox_from_custom_aoi_id(aoi_id)
    if custom is not None:
        return custom
    raise RuntimeError(f"Cannot determine bbox for aoi_id: {aoi_id}")


def _iter_points(coords):
    if not isinstance(coords, (list, tuple)):
        return
    if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        yield float(coords[0]), float(coords[1])
        return
    for part in coords:
        yield from _iter_points(part)


def _validate_bbox_values(b: list[float]) -> list[float]:
    if len(b) != 4:
        raise ValueError("bbox must contain exactly 4 values: min_lon,min_lat,max_lon,max_lat")
    min_lon, min_lat, max_lon, max_lat = b
    if not all(-180.0 <= v <= 180.0 for v in (min_lon, max_lon)):
        raise ValueError("bbox longitude values must be between -180 and 180")
    if not all(-90.0 <= v <= 90.0 for v in (min_lat, max_lat)):
        raise ValueError("bbox latitude values must be between -90 and 90")
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("bbox must satisfy min_lon < max_lon and min_lat < max_lat")
    return [min_lon, min_lat, max_lon, max_lat]


def _parse_bbox_param(bbox: str | None) -> list[float] | None:
    if bbox is None:
        return None
    raw = bbox.strip()
    if not raw:
        return None
    try:
        parts = [float(x.strip()) for x in raw.split(",")]
    except ValueError as exc:
        raise ValueError("bbox must be a comma-separated float string") from exc
    return _validate_bbox_values(parts)


def _parse_polygon_bbox(polygon: str | None) -> list[float] | None:
    if polygon is None:
        return None
    raw = polygon.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("polygon must be valid JSON") from exc

    coords = None
    if isinstance(parsed, dict):
        if parsed.get("type") == "Polygon":
            coords = parsed.get("coordinates")
        elif isinstance(parsed.get("geometry"), dict):
            coords = parsed["geometry"].get("coordinates")
    elif isinstance(parsed, list):
        coords = parsed

    points = list(_iter_points(coords))
    if len(points) < 3:
        raise ValueError("polygon must contain at least 3 coordinate points")

    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return _validate_bbox_values([min(lons), min(lats), max(lons), max(lats)])


def _bbox_from_custom_aoi_id(aoi_id: str) -> list[float] | None:
    if not aoi_id.startswith("custom_"):
        return None
    parts = aoi_id.split("_")
    if len(parts) != 3:
        return None
    try:
        lon = float(parts[1])
        lat = float(parts[2])
    except ValueError:
        return None
    return _validate_bbox_values([
        lon - _CUSTOM_AOI_HALF_SPAN_DEG,
        lat - _CUSTOM_AOI_HALF_SPAN_DEG,
        lon + _CUSTOM_AOI_HALF_SPAN_DEG,
        lat + _CUSTOM_AOI_HALF_SPAN_DEG,
    ])


def _resolve_spatial_bbox(aoi_id: str, bbox: str | None, polygon: str | None) -> list[float] | None:
    parsed_bbox = _parse_bbox_param(bbox)
    if parsed_bbox is not None:
        return parsed_bbox
    polygon_bbox = _parse_polygon_bbox(polygon)
    if polygon_bbox is not None:
        return polygon_bbox
    return _bbox_from_custom_aoi_id(aoi_id)


def _resolve_tile(
    aoi_id: str,
    s2_tile_path: str | None,
    bbox_override: list[float] | None = None,
) -> tuple[Path | None, dict[str, Any] | None]:
    """Pick the Sentinel-2 tile to run inference on.

    Precedence:
        1. Explicit `s2_tile_path` query param (power user / pre-staged tile)
        2. STAC imagery for provided bbox
        3. STAC imagery for resolved AOI bounds
    """
    if s2_tile_path:
        p = Path(s2_tile_path)
        if p.exists():
            return p, {
                "source": "explicit_path",
                "item_id": None,
                "stack_path": str(p),
                "bbox": bbox_override,
            }
        raise RuntimeError(f"ai_detector: provided s2_tile_path does not exist: {p}")

    query_bbox = bbox_override
    if query_bbox is None:
        entry = resolve(aoi_id)
        if entry is not None:
            (west, south), (east, north) = entry["bounds"]
            query_bbox = [west, south, east, north]
        else:
            query_bbox = _bbox_from_custom_aoi_id(aoi_id)

    if query_bbox is not None:
        try:
            from backend.services.stac_service import get_live_or_cached_imagery
            stac_result = get_live_or_cached_imagery(aoi_id, query_bbox)
            if stac_result and "error" not in stac_result:
                paths = stac_result.get("local_paths", {})
                stack = paths.get("stack")
                if stack and Path(stack).exists():
                    return Path(stack), {
                        "source": stac_result.get("source"),
                        "item_id": stac_result.get("id"),
                        "stack_path": stack,
                        "bbox": query_bbox,
                    }
                raise RuntimeError(
                    f"ai_detector: STAC response for {aoi_id} missing usable stack path"
                )
        except Exception as e:  # pragma: no cover — network flake
            raise RuntimeError(f"ai_detector: STAC lookup failed for {aoi_id}: {e}") from e

    return None, None


def detect_macroplastic(
    aoi_id: str,
    s2_tile_path: str | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
) -> dict[str, Any]:
    """Detect sub-pixel plastic patches for an AOI.

    Returns a GeoJSON FeatureCollection dict in the legacy API shape the
    frontend expects.
    """
    bbox_override = _resolve_spatial_bbox(aoi_id, bbox, polygon)
    env_meta: dict[str, Any] | None = get_environment_summary(
        aoi_id,
        _env_bbox_for(aoi_id, bbox_override),
        horizon_hours=72,
        ensure_live=False,
    )

    tile, tile_meta = _resolve_tile(aoi_id, s2_tile_path, bbox_override=bbox_override)
    if tile is None:
        raise RuntimeError(f"ai_detector: no Sentinel-2 tile resolved for {aoi_id}")

    logger.info(
        "ai_detector: imagery selected for %s (source=%s, item_id=%s, stack=%s, bbox=%s)",
        aoi_id,
        (tile_meta or {}).get("source"),
        (tile_meta or {}).get("item_id"),
        (tile_meta or {}).get("stack_path", str(tile)),
        (tile_meta or {}).get("bbox"),
    )

    try:
        from backend.core.config import Settings
        from backend.ml.inference import run_inference

        cfg = Settings()
        fc = run_inference(tile, cfg)
        if env_meta is not None:
            fc, bio_meta = apply_environmental_biofouling(
                fc,
                water_temp_c=float(env_meta["water_temp_c"]),
                chlorophyll_mg_m3=float(env_meta["chlorophyll_mg_m3"]),
            )
            env_meta = {**env_meta, **bio_meta}
        logger.info(
            "ai_detector: real inference OK for %s (tile=%s, features=%d)",
            aoi_id, tile.name, len(fc.features),
        )
        return _detection_fc_to_api_shape(fc, aoi_id, env_meta=env_meta)
    except Exception as e:
        raise RuntimeError(
            f"ai_detector: real inference failed for {aoi_id} (tile={tile}): {e}"
        ) from e
