"""mission_planner — thin service wrapper over backend.mission.planner.plan_mission.

Integration layer:
- Accepts API-shape `detected_geojson` from ai_detector
- Rebuilds a FROZEN DetectionFeatureCollection
- Wraps it in a minimal ForecastEnvelope (no drift frames — scoring
  degrades gracefully to conf*area*fraction * accessibility per D-12)
- Runs the real greedy+2-opt TSP planner with dual (range+time) budget
- Adapts the MissionPlan to the legacy API LineString GeoJSON shape

Mission scoring with no forecast is intentional: the /mission endpoint does
not receive a forecast, so we score purely from detection intrinsics +
distance-to-origin. This matches the `never raise` contract (D-09) and keeps
the API fast (<1 s). For the richer convergence-aware ranking, call
`simulate_drift` → `plan_mission` directly via e2e_test / prebake_demo.

Falls back to mock_data.get_mock_mission_geojson on any error unless strict mode
is enabled.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from backend.services.aoi_registry import origin_for
from backend.services.mock_data import get_mock_mission_geojson
from backend.services.runtime_flags import strict_mode_enabled

logger = logging.getLogger(__name__)


def _api_shape_to_detection_fc(api_fc: dict[str, Any]):
    """Reconstruct a DetectionFeatureCollection from the legacy API dict shape."""
    from backend.core.schemas import (
        DetectionFeature,
        DetectionFeatureCollection,
        DetectionProperties,
    )
    from geojson_pydantic import Polygon

    features: list[DetectionFeature] = []
    for api_feat in api_fc.get("features", []):
        p = api_feat.get("properties", {})
        conf = float(p.get("confidence", 0.5))
        age = int(p.get("age_days", p.get("age_days_est", 0)))
        area = float(p.get("area_sq_meters", p.get("area_m2", 200.0)))
        frac = float(p.get("fraction_plastic", min(conf, 1.0)))
        features.append(DetectionFeature(
            type="Feature",
            geometry=Polygon(**api_feat["geometry"]),
            properties=DetectionProperties(
                conf_raw=min(max(conf, 0.0), 1.0),
                conf_adj=min(max(conf, 0.0), 1.0),
                fraction_plastic=min(max(frac, 0.0), 1.0),
                area_m2=max(area, 0.0),
                age_days_est=max(age, 0),
            ),
        ))
    return DetectionFeatureCollection(type="FeatureCollection", features=features)


def _mission_to_api_shape(plan, aoi_id: str) -> dict[str, Any]:
    """Adapt FROZEN MissionPlan → legacy API LineString FeatureCollection.

    Legacy shape: single Feature with LineString geometry + `mission_id`,
    `estimated_vessel_time_hours`, `priority` properties.
    """
    # MissionPlan.route is a Feature[LineString, dict] — pull its geometry.
    route = plan.route
    if hasattr(route, "model_dump"):
        route_dict = route.model_dump()
    else:
        route_dict = dict(route)

    geometry = route_dict.get("geometry", {"type": "LineString", "coordinates": []})
    # Ensure coordinates is a list (pydantic may have emitted tuples).
    coords = geometry.get("coordinates", [])
    geometry = {
        "type": "LineString",
        "coordinates": [[float(c[0]), float(c[1])] for c in coords],
    }

    # Priority label: HIGH if any waypoint has priority_score > median, else MEDIUM.
    if plan.waypoints:
        scores = [w.priority_score for w in plan.waypoints]
        top = max(scores) if scores else 0.0
        priority_label = "HIGH" if top > 0 else "LOW"
    else:
        priority_label = "LOW"

    line_feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "mission_id": f"OP_{aoi_id.upper()}",
            "estimated_vessel_time_hours": round(plan.total_hours, 2),
            "priority": priority_label,
            "total_distance_km": round(plan.total_distance_km, 2),
            "waypoint_count": len(plan.waypoints),
            # Optional per-waypoint payload for richer UI (not expected by current FE).
            "waypoints": [
                {
                    "order": w.order,
                    "lon": w.lon,
                    "lat": w.lat,
                    "arrival_hour": round(w.arrival_hour, 2),
                    "priority_score": round(w.priority_score, 3),
                }
                for w in plan.waypoints
            ],
        },
    }
    return {"type": "FeatureCollection", "features": [line_feature]}


def calculate_cleanup_mission_plan(detected_geojson: dict[str, Any], aoi_id: str):
    """Like `calculate_cleanup_mission` but returns the FROZEN `MissionPlan`
    pydantic object instead of the legacy API dict shape. Used by the
    /mission/export endpoint which needs the strongly-typed plan for
    `export_gpx`/`export_geojson`/`export_pdf`. Returns None on failure
    so the caller can fall back gracefully.
    """
    if not detected_geojson.get("features"):
        return None
    try:
        from backend.core.config import Settings
        from backend.core.schemas import ForecastEnvelope
        from backend.mission.planner import plan_mission

        cfg = Settings()
        origin = origin_for(aoi_id)
        detections_fc = _api_shape_to_detection_fc(detected_geojson)
        if not detections_fc.features:
            return None
        envelope = ForecastEnvelope(
            source_detections=detections_fc,
            frames=[],
            windage_alpha=cfg.physics.windage_alpha,
        )
        return plan_mission(
            envelope,
            vessel_range_km=200.0,
            hours=8.0,
            origin=origin,
            cfg=cfg,
        )
    except Exception as e:
        logger.warning("mission_planner: plan construction failed for %s: %s", aoi_id, e)
        return None


def calculate_cleanup_mission(
    detected_geojson: dict[str, Any],
    aoi_id: str,
) -> dict[str, Any]:
    """Plan an optimal cleanup route from detections.

    Falls back to mock mission on failures unless strict mode is enabled.
    """
    strict = strict_mode_enabled()

    if os.environ.get("DRIFT_FORCE_MOCK", "").strip() == "1":
        logger.info("mission_planner: DRIFT_FORCE_MOCK=1 → mock mission for %s", aoi_id)
        return get_mock_mission_geojson(aoi_id)

    if not detected_geojson.get("features"):
        if strict:
            raise RuntimeError(
                f"mission_planner: zero detections for {aoi_id}; strict mode disallows mock fallback"
            )
        logger.info("mission_planner: zero detections for %s → mock mission", aoi_id)
        return get_mock_mission_geojson(aoi_id)

    try:
        from backend.core.config import Settings
        from backend.core.schemas import ForecastEnvelope
        from backend.mission.planner import plan_mission

        cfg = Settings()
        origin = origin_for(aoi_id)

        detections_fc = _api_shape_to_detection_fc(detected_geojson)
        if not detections_fc.features:
            if strict:
                raise RuntimeError(
                    f"mission_planner: detection conversion dropped all features for {aoi_id}"
                )
            return get_mock_mission_geojson(aoi_id)

        # Minimal envelope: source_detections + no drift frames.
        # Scoring degrades to (conf_adj * area_m2 * fraction_plastic) * accessibility.
        envelope = ForecastEnvelope(
            source_detections=detections_fc,
            frames=[],
            windage_alpha=cfg.physics.windage_alpha,
        )

        plan = plan_mission(
            envelope,
            vessel_range_km=200.0,
            hours=8.0,
            origin=origin,
            cfg=cfg,
        )
        logger.info(
            "mission_planner: real planner OK for %s (waypoints=%d, dist=%.1f km, hours=%.1f)",
            aoi_id, len(plan.waypoints), plan.total_distance_km, plan.total_hours,
        )
        return _mission_to_api_shape(plan, aoi_id)
    except Exception as e:
        if strict:
            raise RuntimeError(f"mission_planner: real planner failed for {aoi_id}: {e}") from e
        logger.warning(
            "mission_planner: real planner failed for %s: %s → mock", aoi_id, e,
        )
        return get_mock_mission_geojson(aoi_id)
