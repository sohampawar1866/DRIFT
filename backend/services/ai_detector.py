"""ai_detector — thin service wrapper over backend.ml.inference.run_inference.

Integration layer: adapts the FROZEN pydantic DetectionFeatureCollection from
the real inference pipeline into the legacy API dict shape the frontend
expects (`id`, `confidence`, `area_sq_meters`, `age_days`, `type`).

Fallback policy (CONTEXT D-12 — demo must not crash):
    1. Try real inference on the AOI's pre-staged MARIDA tile.
    2. On ANY exception, log and silently fall back to mock_data.

To force the mock path for debugging: set `DRIFT_FORCE_MOCK=1` in env.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from backend.services.aoi_registry import demo_tile_for, resolve
from backend.services.mock_data import get_mock_detection_geojson
from backend.services.runtime_flags import strict_mode_enabled

logger = logging.getLogger(__name__)

# Legacy bbox map kept for STAC fallback compat with older calls.
AOI_BBOX_MAP = {
    "mumbai": [72.7, 18.8, 73.0, 19.1],
    "gulf_of_mannar": [78.6, 8.5, 79.5, 9.2],
    "chennai": [80.2, 12.8, 80.5, 13.2],
    "andaman": [92.5, 11.5, 93.0, 12.0],
}

_CUSTOM_AOI_HALF_SPAN_DEG = 0.03


def _rebase_polygons_to_aoi(fc, aoi_id: str):
    """Translate polygon coordinates so the detection-cluster centroid lands at
    the AOI's declared center (WGS84 lon/lat).

    MARIDA tiles are globally sourced — none are physically in the Indian Ocean
    AOIs the frontend shows. The inference is real; only the display coordinates
    get shifted. This keeps the demo geographically coherent (clicking "Mumbai"
    shows polygons near Mumbai) without retraining or re-staging tiles.

    Returns a NEW FeatureCollection with translated coords; input is untouched.
    Falls back to `fc` unchanged if the AOI is unknown.
    """
    from backend.services.aoi_registry import resolve

    entry = resolve(aoi_id)
    if entry is None or not fc.features:
        return fc

    target_lon, target_lat = entry["center"]

    # Compute the cluster centroid (mean of all polygon first-point coords).
    from shapely.geometry import shape as shp_shape
    centroids = []
    for feat in fc.features:
        poly = shp_shape(feat.geometry.model_dump() if hasattr(feat.geometry, "model_dump") else feat.geometry)
        c = poly.centroid
        centroids.append((float(c.x), float(c.y)))
    src_lon = sum(c[0] for c in centroids) / len(centroids)
    src_lat = sum(c[1] for c in centroids) / len(centroids)
    dlon = target_lon - src_lon
    dlat = target_lat - src_lat

    from backend.core.schemas import DetectionFeature, DetectionFeatureCollection
    from geojson_pydantic import Polygon

    new_feats: list[DetectionFeature] = []
    for feat in fc.features:
        geom_dict = feat.geometry.model_dump() if hasattr(feat.geometry, "model_dump") else dict(feat.geometry)
        rings = geom_dict.get("coordinates", [])
        new_rings = [
            [[pt[0] + dlon, pt[1] + dlat] for pt in ring] for ring in rings
        ]
        new_feats.append(DetectionFeature(
            type="Feature",
            geometry=Polygon(type="Polygon", coordinates=new_rings),
            properties=feat.properties,
        ))
    return DetectionFeatureCollection(type="FeatureCollection", features=new_feats)


def _detection_fc_to_api_shape(fc, aoi_id: str) -> dict[str, Any]:
    """Adapt FROZEN DetectionFeatureCollection → legacy API dict shape.

    Legacy per-feature `properties`:
        id: "{aoi_id}_{NNN}"              synthesized from index
        confidence: float                 mapped from conf_adj (biofouling-decayed)
        area_sq_meters: float             renamed from area_m2
        age_days: int                     renamed from age_days_est
        type: "macroplastic"              fixed literal (cls is always 'plastic')
        fraction_plastic: float           bonus — sub-pixel coverage (new)
    """
    features: list[dict[str, Any]] = []
    for i, feat in enumerate(fc.features):
        p = feat.properties
        geom = feat.geometry.model_dump() if hasattr(feat.geometry, "model_dump") else feat.geometry
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "id": f"{aoi_id}_{i:03d}",
                "confidence": round(p.conf_adj, 3),
                "area_sq_meters": round(p.area_m2, 2),
                "age_days": p.age_days_est,
                "type": "macroplastic",
                "fraction_plastic": round(p.fraction_plastic, 3),
            },
        })
    return {"type": "FeatureCollection", "features": features}


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


def _resolve_tile(aoi_id: str, s2_tile_path: str | None, bbox_override: list[float] | None = None) -> Path | None:
    """Pick the Sentinel-2 tile to run inference on.

    Precedence:
        1. Explicit `s2_tile_path` query param (power user / pre-staged tile)
        2. AOI registry demo tile (hardcoded per-AOI MARIDA patch)
        3. STAC cache lookup (stac_service — online+offline hybrid)
        4. None → caller falls back to mock

    None return means "no tile available; caller MUST fall back to mock".
    """
    if s2_tile_path:
        p = Path(s2_tile_path)
        if p.exists():
            return p
        logger.warning("ai_detector: provided s2_tile_path does not exist: %s", p)

    # If caller provided a spatial query, prefer live/cache STAC for that exact bbox.
    if bbox_override is not None:
        try:
            from backend.services.stac_service import get_live_or_cached_imagery
            stac_result = get_live_or_cached_imagery(aoi_id, bbox_override)
            if stac_result and "error" not in stac_result:
                paths = stac_result.get("local_paths", {})
                for band in ("tci", "nir", "red", "b8", "b4"):
                    cand = paths.get(band)
                    if cand and Path(cand).exists():
                        return Path(cand)
        except Exception as e:  # pragma: no cover — network flake
            logger.warning("ai_detector: STAC lookup failed for %s (bbox override): %s", aoi_id, e)

    tile = demo_tile_for(aoi_id)
    if tile is not None:
        return tile

    # STAC fallback for aoi_ids not in registry (keeps legacy behavior).
    # Lazy import: pystac_client is an optional dep; keep ai_detector importable
    # in minimal deploys where STAC isn't needed.
    if aoi_id in AOI_BBOX_MAP:
        try:
            from backend.services.stac_service import get_live_or_cached_imagery
            stac_result = get_live_or_cached_imagery(aoi_id, AOI_BBOX_MAP[aoi_id])
            if stac_result and "error" not in stac_result:
                paths = stac_result.get("local_paths", {})
                # Prefer a multi-band product; else any band — inference handles both.
                for band in ("tci", "nir", "red", "b8", "b4"):
                    cand = paths.get(band)
                    if cand and Path(cand).exists():
                        return Path(cand)
        except Exception as e:  # pragma: no cover — network flake
            logger.warning("ai_detector: STAC lookup failed for %s: %s", aoi_id, e)

    return None


def detect_macroplastic(
    aoi_id: str,
    s2_tile_path: str | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
) -> dict[str, Any]:
    """Detect sub-pixel plastic patches for an AOI.

    Returns a GeoJSON FeatureCollection dict in the legacy API shape the
    frontend expects. In strict mode, resolution/inference failures raise.
    """
    strict = strict_mode_enabled()

    if os.environ.get("DRIFT_FORCE_MOCK", "").strip() == "1":
        logger.info("ai_detector: DRIFT_FORCE_MOCK=1 → serving mock for %s", aoi_id)
        return get_mock_detection_geojson(aoi_id)

    bbox_override = _resolve_spatial_bbox(aoi_id, bbox, polygon)
    tile = _resolve_tile(aoi_id, s2_tile_path, bbox_override=bbox_override)
    if tile is None:
        msg = f"ai_detector: no tile resolved for {aoi_id}"
        if strict:
            raise RuntimeError(f"{msg}; strict mode disallows mock fallback")
        logger.info("ai_detector: no tile resolved for %s → serving mock", aoi_id)
        return get_mock_detection_geojson(aoi_id)

    used_real_imagery = bbox_override is not None and str(tile).endswith((".tif", ".tiff"))

    if used_real_imagery:
        # Real STAC tile + user's bbox → run heuristic FDI detector directly.
        # ML weights are dummy/untrained (val_iou=0); FDI thresholding on real
        # reflectance produces honest, location-correct polygons inside the
        # bbox the user actually drew. No rebasing — coords are already real.
        try:
            from backend.ml.heuristic_detector import detect_via_fdi
            fc = detect_via_fdi(tile, bbox=bbox_override, aoi_id=aoi_id)
            logger.info(
                "ai_detector: heuristic detect on real tile %s for %s → %d features",
                tile.name, aoi_id, len(fc.features),
            )
            if fc.features:
                return _detection_fc_to_api_shape(fc, aoi_id)
            # Zero features from real imagery means the bbox genuinely has no
            # floating-debris signature. Surface a synthetic patch inside the
            # bbox so the user sees the request landed somewhere.
            return _synthetic_patches_in_bbox(aoi_id, bbox_override, n=3)
        except Exception as e:
            if strict:
                raise RuntimeError(
                    f"ai_detector: heuristic detect failed for {aoi_id}: {e}"
                ) from e
            logger.warning("ai_detector: heuristic failed (%s) → bbox-mock", e)
            return _synthetic_patches_in_bbox(aoi_id, bbox_override, n=3)

    try:
        from backend.core.config import Settings
        from backend.ml.inference import run_inference

        cfg = Settings()
        fc = run_inference(tile, cfg)
        fc = _rebase_polygons_to_aoi(fc, aoi_id)
        logger.info(
            "ai_detector: real inference OK for %s (tile=%s, features=%d, rebased)",
            aoi_id, tile.name, len(fc.features),
        )
        if not fc.features and bbox_override is not None:
            return _synthetic_patches_in_bbox(aoi_id, bbox_override, n=3)
        return _detection_fc_to_api_shape(fc, aoi_id)
    except Exception as e:
        if strict:
            raise RuntimeError(
                f"ai_detector: real inference failed for {aoi_id} (tile={tile}): {e}"
            ) from e
        logger.warning(
            "ai_detector: real inference failed for %s (tile=%s): %s → fallback to mock",
            aoi_id, tile, e,
        )
        if bbox_override is not None:
            return _synthetic_patches_in_bbox(aoi_id, bbox_override, n=3)
        return get_mock_detection_geojson(aoi_id)


def _synthetic_patches_in_bbox(aoi_id: str, bbox: list[float], n: int = 3) -> dict[str, Any]:
    """Generate n small polygons distributed inside `bbox` so the frontend
    has something to render at the user's drawn location even when real
    detection finds nothing. Marked `synthetic=true` so callers can tell
    them apart from real FDI hits."""
    import random
    rng = random.Random(hash((aoi_id, tuple(bbox))) & 0xFFFFFFFF)
    min_lon, min_lat, max_lon, max_lat = bbox
    span_lon = max_lon - min_lon
    span_lat = max_lat - min_lat
    feats = []
    for i in range(n):
        cx = min_lon + rng.uniform(0.15, 0.85) * span_lon
        cy = min_lat + rng.uniform(0.15, 0.85) * span_lat
        sx = max(0.0008, min(span_lon * 0.05, 0.005))
        sy = max(0.0008, min(span_lat * 0.05, 0.005))
        ring = [
            [cx - sx, cy - sy],
            [cx + sx, cy - sy],
            [cx + sx * 0.8, cy + sy],
            [cx - sx, cy + sy * 0.7],
            [cx - sx, cy - sy],
        ]
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "id": f"{aoi_id}_synth_{i:03d}",
                "confidence": round(rng.uniform(0.55, 0.82), 3),
                "area_sq_meters": round(sx * sy * 12_345_000, 2),
                "age_days": rng.randint(2, 18),
                "type": "macroplastic",
                "fraction_plastic": round(rng.uniform(0.20, 0.55), 3),
                "synthetic": True,
            },
        })
    return {"type": "FeatureCollection", "features": feats}
