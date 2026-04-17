"""Main FastAPI routes (v1).

Every handler delegates to the service layer (`backend.services.*`). The service
layer runs the REAL intelligence pipeline (backend.ml / physics / mission) and
silently falls back to `mock_data` on any failure (CONTEXT D-12 — demo-safe).

Endpoints
---------
GET  /api/v1/aois                        list AOIs for the frontend dropdown
GET  /api/v1/detect                       run_inference on MARIDA tile → polygons
GET  /api/v1/forecast                     detect → forecast_drift (Euler tracker)
GET  /api/v1/mission                      detect → plan_mission (greedy+2-opt TSP)
GET  /api/v1/mission/export               GPX | GeoJSON | PDF (real export.py)
GET  /api/v1/dashboard/metrics            summary stats (real when available)

Env toggle: `DRIFT_FORCE_MOCK=1` pins every endpoint to the legacy mock data.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from backend.services.ai_detector import detect_macroplastic
from backend.services.drift_engine import simulate_drift
from backend.services.mission_planner import (
    calculate_cleanup_mission,
    calculate_cleanup_mission_plan,
)
from backend.services.aoi_registry import list_aois as registry_list_aois
from backend.services.mock_data import (
    get_mock_aois,
    get_mock_dashboard_metrics,
)
from backend.services.runtime_flags import strict_mode_enabled

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _as_http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _run_detection(
    aoi_id: str,
    *,
    s2_tile_path: str | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
) -> dict:
    try:
        return detect_macroplastic(aoi_id, s2_tile_path=s2_tile_path, bbox=bbox, polygon=polygon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc


@router.get("/aois")
async def list_aois():
    """Return pre-staged AOIs (frontend dropdown).

    Prefers the canonical aoi_registry (gulf_of_mannar, mumbai_offshore,
    bay_of_bengal_mouth, arabian_sea_gyre_edge). Falls back to mock_data
    if the registry is empty for some reason.
    """
    registry = registry_list_aois()
    if registry:
        return {"aois": registry}
    return get_mock_aois()


@router.get("/detect")
async def detect_plastic(
    aoi_id: str = "mumbai",
    s2_tile_path: str | None = None,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Run the real plastic-detection pipeline on a MARIDA tile for the AOI.

    Returns a GeoJSON FeatureCollection with properties
    `{id, confidence, area_sq_meters, age_days, type, fraction_plastic}`.
    Silent fallback to mock data on any inference failure.
    """
    return _run_detection(aoi_id, s2_tile_path=s2_tile_path, bbox=bbox, polygon=polygon)


@router.get("/forecast")
async def forecast_drift(
    aoi_id: str = "mumbai",
    hours: int = 24,
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Detect → tracker. Returns drifted particle positions + density contours
    for the requested horizon (+24/+48/+72 h).
    """
    if hours not in (24, 48, 72):
        raise HTTPException(status_code=400,
                            detail="Invalid forecast step. Allowed: 24, 48, 72.")
    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    try:
        return simulate_drift(base_detect, aoi_id, hours)
    except RuntimeError as exc:
        raise _as_http_error(exc) from exc


@router.get("/mission")
async def plan_mission(
    aoi_id: str = "mumbai",
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
async def get_dashboard_stats(
    aoi_id: str = "mumbai",
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Aggregated stats + biofouling-vs-age chart data for UI side-panels.

    Derives totals from the real detection call when it produces features;
    falls back to `mock_data.get_mock_dashboard_metrics` otherwise.
    """
    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    feats = base_detect.get("features", [])
    if not feats:
        return get_mock_dashboard_metrics(aoi_id)

    total_area = sum(f["properties"].get("area_sq_meters", 0.0) for f in feats)
    confs = [f["properties"].get("confidence", 0.0) for f in feats]
    avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0
    high_priority = sum(1 for c in confs if c >= 0.75)

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
        "biofouling_chart_data": biofouling_chart,
    }


@router.get("/mission/export")
async def export_mission_file(
    aoi_id: str = "mumbai",
    format: str = "gpx",
    bbox: str | None = None,
    polygon: str | None = None,
):
    """Download the cleanup mission as GPX (Coast Guard nav), GeoJSON, or PDF briefing.

    Uses the real `backend.mission.export` module (matplotlib + reportlab +
    stdlib GPX). Falls back to a minimal GPX rendered from the mock mission
    if the real export pipeline can't produce a plan.
    """
    fmt = format.lower().strip()
    if fmt not in ("gpx", "geojson", "json", "pdf"):
        raise HTTPException(status_code=400,
                            detail="format must be one of: gpx, geojson, pdf")
    if fmt == "json":
        fmt = "geojson"

    strict = strict_mode_enabled()

    base_detect = _run_detection(aoi_id, bbox=bbox, polygon=polygon)
    plan = calculate_cleanup_mission_plan(base_detect, aoi_id)

    if plan is None or not plan.waypoints:
        if strict:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No mission plan could be constructed from detections; "
                    "strict mode disallows mock export fallback"
                ),
            )
        # Fall back to mock-mission GPX/JSON — prevents broken downloads mid-demo.
        logger.info("export: no real plan for %s → mock mission payload (%s)", aoi_id, fmt)
        mock_mission = calculate_cleanup_mission(base_detect, aoi_id)
        if fmt == "geojson":
            return mock_mission
        coords = mock_mission["features"][0]["geometry"]["coordinates"]
        xml = _minimal_gpx(coords, aoi_id)
        return Response(
            content=xml,
            media_type="application/gpx+xml",
            headers={"Content-Disposition":
                     f'attachment; filename="drift_mission_{aoi_id}.gpx"'},
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
        if strict:
            raise HTTPException(
                status_code=500,
                detail=f"Mission export failed in strict mode: {e}",
            ) from e
        logger.warning("export: %s format failed for %s: %s", fmt, aoi_id, e)
        coords = plan.route.model_dump().get("geometry", {}).get("coordinates", [])
        xml = _minimal_gpx(coords, aoi_id)
        return Response(
            content=xml,
            media_type="application/gpx+xml",
            headers={"Content-Disposition":
                     f'attachment; filename="drift_mission_{aoi_id}.gpx"'},
        )


def _minimal_gpx(coords: list, aoi_id: str) -> str:
    """Hand-rolled GPX fallback for when the real export module is unavailable."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="DRIFT">',
        '  <trk>',
        f'    <name>DRIFT Cleanup Mission — {aoi_id}</name>',
        '    <trkseg>',
    ]
    for pt in coords:
        if len(pt) >= 2:
            lines.append(f'      <trkpt lat="{pt[1]}" lon="{pt[0]}"></trkpt>')
    lines += ["    </trkseg>", "  </trk>", "</gpx>"]
    return "\n".join(lines)
