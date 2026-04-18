"""Main FastAPI routes (v1).

Every handler delegates to the service layer (`backend.services.*`). The service
layer runs the real intelligence pipeline (backend.ml / physics / mission).

Endpoints
---------
GET  /api/v1/aois                        list AOIs (coordinate-based)
GET  /api/v1/detect                       run inference on Sentinel-2 tile → polygons
GET  /api/v1/forecast                     detect → forecast_drift (Euler tracker)
GET  /api/v1/mission                      detect → plan_mission (greedy+2-opt TSP)
GET  /api/v1/mission/export               GPX | GeoJSON | PDF (real export.py)
GET  /api/v1/dashboard/metrics            summary stats
"""
from __future__ import annotations

import json
import logging
import math
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.services.ai_detector import detect_macroplastic
from backend.services.alert_service import evaluate_deposition_alerts
from backend.services.env_service import get_environment_summary
from backend.services.drift_engine import simulate_drift
from backend.services.mission_planner import (
    calculate_cleanup_mission,
    calculate_cleanup_mission_plan,
)
from backend.services.aoi_registry import list_aois as registry_list_aois, resolve as registry_resolve

_CUSTOM_AOI_HALF_SPAN_DEG = 0.03

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _as_http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


_detection_lock = threading.Lock()

@lru_cache(maxsize=32)
def _locked_run_detection(
    aoi_id: str, s2_tile_path: str | None, bbox: str | None, polygon: str | None
) -> dict:
    try:
        return detect_macroplastic(aoi_id, s2_tile_path=s2_tile_path, bbox=bbox, polygon=polygon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc

def _run_detection(
    aoi_id: str,
    *,
    s2_tile_path: str | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
) -> dict:
    with _detection_lock:
        return _locked_run_detection(aoi_id, s2_tile_path, bbox, polygon)


def _parse_bbox_str(raw: str | None) -> list[float] | None:
    if raw is None or not raw.strip():
        return None
    parts = [float(x.strip()) for x in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must have 4 comma-separated numbers")
    min_lon, min_lat, max_lon, max_lat = parts
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("bbox must satisfy min_lon < max_lon and min_lat < max_lat")
    return parts


def _parse_polygon_bbox(raw_polygon: str | None) -> list[float] | None:
    if raw_polygon is None or not raw_polygon.strip():
        return None
    parsed = json.loads(raw_polygon)
    coords = parsed
    if isinstance(parsed, dict):
        if parsed.get("type") == "Polygon":
            coords = parsed.get("coordinates", [])
        elif isinstance(parsed.get("geometry"), dict):
            coords = parsed["geometry"].get("coordinates", [])
    points: list[tuple[float, float]] = []

    def walk(node):
        if isinstance(node, (list, tuple)) and len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
            points.append((float(node[0]), float(node[1])))
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(coords)
    if len(points) < 3:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return [min(lons), min(lats), max(lons), max(lats)]


def _request_bbox(aoi_id: str, bbox: str | None, polygon: str | None) -> list[float]:
    """Resolve the bounding box from explicit params or the AOI ID."""
    parsed = _parse_bbox_str(bbox)
    if parsed is not None:
        return parsed
    poly_bbox = _parse_polygon_bbox(polygon)
    if poly_bbox is not None:
        return poly_bbox
    entry = registry_resolve(aoi_id)
    if entry is not None:
        (west, south), (east, north) = entry["bounds"]
        return [west, south, east, north]
    # Parse custom_{lon}_{lat} format
    if aoi_id.startswith("custom_"):
        parts = aoi_id.split("_")
        if len(parts) == 3:
            try:
                lon, lat = float(parts[1]), float(parts[2])
                return [
                    lon - _CUSTOM_AOI_HALF_SPAN_DEG,
                    lat - _CUSTOM_AOI_HALF_SPAN_DEG,
                    lon + _CUSTOM_AOI_HALF_SPAN_DEG,
                    lat + _CUSTOM_AOI_HALF_SPAN_DEG,
                ]
            except ValueError:
                pass
    raise HTTPException(status_code=400, detail=f"Cannot determine bbox for aoi_id: {aoi_id}")


def _bbox_area_m2(bbox_vals: list[float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox_vals
    lat_mid = (min_lat + max_lat) / 2.0
    width_m = abs(max_lon - min_lon) * 111_320.0 * math.cos(math.radians(lat_mid))
    height_m = abs(max_lat - min_lat) * 110_540.0
    return max(width_m * height_m, 1.0)


@router.get("/aois")
def list_aois():
    """Return available AOIs. Returns an empty list when using coordinate-based selection."""
    return {"aois": registry_list_aois()}


@router.get("/detect")
def detect_plastic(
    aoi_id: str,
    s2_tile_path: str | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Run the plastic-detection pipeline on a Sentinel-2 tile for the AOI.

    Returns a GeoJSON FeatureCollection with properties
    `{id, confidence, area_sq_meters, age_days, type, fraction_plastic}`.
    """
    return _run_detection(aoi_id, s2_tile_path=s2_tile_path, bbox=bbox, polygon=polygon)


@router.get("/forecast")
def forecast_drift(
    aoi_id: str,
    hours: int = 24,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Detect → tracker. Returns drifted particle positions + density contours
    for the requested horizon (+24/+48/+72 h).
    """
    if hours < 24 or hours > 2160 or hours % 24 != 0:
        raise HTTPException(status_code=400,
                            detail="Invalid forecast step. Allowed: multiples of 24 in [24, 2160].")
    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    try:
        return simulate_drift(base_detect, aoi_id, hours)
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc


@router.get("/mission")
def plan_mission(
    aoi_id: str,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Detect → greedy+2-opt TSP. Returns a closed vessel route with waypoints."""
    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    try:
        return calculate_cleanup_mission(base_detect, aoi_id)
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc


@router.get("/dashboard/metrics")
def get_dashboard_stats(
    aoi_id: str,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Aggregated stats + biofouling-vs-age chart data for UI side-panels.

    Derives totals from the real detection call.
    """
    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    feats = base_detect.get("features", [])

    total_area = sum(f["properties"].get("area_sq_meters", 0.0) for f in feats)
    confs = [f["properties"].get("confidence", 0.0) for f in feats]
    avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0
    high_priority = sum(1 for c in confs if c >= 0.75)

    region_bbox = _request_bbox(aoi_id, bbox, polygon)
    region_area_m2 = _bbox_area_m2(region_bbox)
    coverage_pct = min(100.0, (total_area / region_area_m2) * 100.0)

    try:
        env_summary = get_environment_summary(
            aoi_id,
            region_bbox,
            horizon_hours=72,
            ensure_live=False,
        )
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc

    # Biofouling decay chart: mirrors the model's conf_adj = conf_raw * exp(-age/30).
    import math
    biofouling_chart = [
        {"age_days": d, "simulated_confidence": round(math.exp(-d / 30.0), 3)}
        for d in (1, 5, 15, 30, 40)
    ]

    return {
        "summary": {
            "total_area_sq_meters": round(total_area, 2),
            "total_patches": len(feats),
            "avg_confidence": avg_conf,
            "high_priority_targets": high_priority,
        },
        "region_statistics": {
            "plastic_coverage_pct": round(coverage_pct, 3),
            "average_confidence": avg_conf,
            "area_m2": round(region_area_m2, 2),
        },
        "environment": env_summary,
        "biofouling_chart_data": biofouling_chart,
    }


@router.get("/environment")
def get_environment_context(
    aoi_id: str,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Return environmental context used by biofouling/forecast layers."""
    try:
        req_bbox = _request_bbox(aoi_id, bbox, polygon)
        return get_environment_summary(
            aoi_id,
            req_bbox,
            horizon_hours=72,
            ensure_live=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc


@router.get("/alerts/preview")
def preview_deposition_alerts(
    aoi_id: str,
    hours: int = 360,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Evaluate deposition hotspot alerts for nearest conservation responders."""
    if hours < 24 or hours > 2160 or hours % 24 != 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid forecast step. Allowed: multiples of 24 in [24, 2160].",
        )
    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    try:
        forecast = simulate_drift(base_detect, aoi_id, hours)
        alert_payload = evaluate_deposition_alerts(
            forecast,
            aoi_id=aoi_id,
            forecast_hours=hours,
        )
        return {
            "status": "ok",
            "alerts": alert_payload,
        }
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc


@router.get("/mission/export")
def export_mission_file(
    aoi_id: str,
    format: str = "gpx",
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Download the cleanup mission as GPX (Coast Guard nav), GeoJSON, or PDF briefing.

    Uses the real `backend.mission.export` module (matplotlib + reportlab +
    stdlib GPX).
    """
    fmt = format.lower().strip()
    if fmt not in ("gpx", "geojson", "json", "pdf"):
        raise HTTPException(status_code=400,
                            detail="format must be one of: gpx, geojson, pdf")
    if fmt == "json":
        fmt = "geojson"

    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    plan = calculate_cleanup_mission_plan(base_detect, aoi_id)

    if plan is None or not plan.waypoints:
        raise HTTPException(
            status_code=422,
            detail="No mission plan could be constructed from detections",
        )

    # Real export pipeline
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"drift_export_{aoi_id}_"))
    try:
        if fmt == "gpx":
            from backend.mission.export import export_gpx
            out = tmp_dir / f"drift_mission_{aoi_id}.gpx"
            export_gpx(plan, out)
            return FileResponse(
                path=str(out),
                media_type="application/gpx+xml",
                filename=out.name,
            )
        if fmt == "geojson":
            from backend.mission.export import export_geojson
            out = tmp_dir / f"drift_mission_{aoi_id}.geojson"
            export_geojson(plan, out)
            return FileResponse(
                path=str(out),
                media_type="application/geo+json",
                filename=out.name,
            )
        if fmt == "pdf":
            from backend.mission.export import export_pdf
            out = tmp_dir / f"drift_mission_{aoi_id}.pdf"
            # Run without a forecast envelope — PDF degrades to waypoint table +
            # coastline map + fuel/time summary (no currents overlay).
            export_pdf(plan, None, out)
            return FileResponse(
                path=str(out),
                media_type="application/pdf",
                filename=out.name,
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Mission export failed: {e}",
        ) from e
