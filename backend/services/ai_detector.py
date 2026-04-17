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


def _resolve_tile(aoi_id: str, s2_tile_path: str | None) -> Path | None:
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
                for band in ("tci", "red", "nir", "b8", "b4"):
                    cand = paths.get(band)
                    if cand and Path(cand).exists():
                        return Path(cand)
        except Exception as e:  # pragma: no cover — network flake
            logger.warning("ai_detector: STAC lookup failed for %s: %s", aoi_id, e)

    return None


def detect_macroplastic(aoi_id: str, s2_tile_path: str | None = None) -> dict[str, Any]:
    """Detect sub-pixel plastic patches for an AOI.

    Returns a GeoJSON FeatureCollection dict in the legacy API shape the
    frontend expects. In strict mode, resolution/inference failures raise.
    """
    strict = strict_mode_enabled()

    if os.environ.get("DRIFT_FORCE_MOCK", "").strip() == "1":
        logger.info("ai_detector: DRIFT_FORCE_MOCK=1 → serving mock for %s", aoi_id)
        return get_mock_detection_geojson(aoi_id)

    tile = _resolve_tile(aoi_id, s2_tile_path)
    if tile is None:
        msg = f"ai_detector: no tile resolved for {aoi_id}"
        if strict:
            raise RuntimeError(f"{msg}; strict mode disallows mock fallback")
        logger.info("ai_detector: no tile resolved for %s → serving mock", aoi_id)
        return get_mock_detection_geojson(aoi_id)

    try:
        # Lazy import — keeps the service importable even if heavy ML deps fail
        # (e.g. torch missing in a minimal API-only deploy). Fallback still works.
        from backend.core.config import Settings
        from backend.ml.inference import run_inference

        cfg = Settings()
        fc = run_inference(tile, cfg)
        fc = _rebase_polygons_to_aoi(fc, aoi_id)
        logger.info(
            "ai_detector: real inference OK for %s (tile=%s, features=%d, rebased)",
            aoi_id, tile.name, len(fc.features),
        )
        # If the model produced zero detections, the API shape is still valid
        # ({features:[]}). Frontend will handle it gracefully.
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
        return get_mock_detection_geojson(aoi_id)
